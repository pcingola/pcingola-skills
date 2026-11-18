"""Apply a sequence of operations to a deck in one call, atomically.

Each operation is parsed into its typed form (`edit_operations`) and runs the core
function of the command of the same name. `edit` buys two things a shell chain of
separate invocations cannot:

- **No temp files to thread.** Nine operations used to mean nine intermediate
  decks and nine paths to keep straight.
- **Atomicity.** Every step writes inside a temporary directory; the output path
  is only touched at the end, by `Path.replace`, which is atomic on the same
  filesystem. A failure at step 7 of 9 leaves no half-written deck behind: not a
  truncated file, not a stale one, nothing.

Every action name is the name of a command. `add-text` runs `add-text`. There is
no separate action vocabulary to keep in sync with the CLI.

The CLI prints each step as the command of that step prints its report, with the
step's temporary deck as the output path, and a failed step as that command
prints its error.
"""

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cmd_add_chart import print_chart_added
from .cmd_add_images import print_add_images_failure, print_images_added
from .cmd_add_notes import print_notes_set
from .cmd_add_slide import print_added_slides
from .cmd_add_table import print_tables_added
from .cmd_add_text import print_add_text_failure, print_text_added
from .cmd_copy_slide import print_copied_slides, print_copy_slide_failure
from .cmd_delete_slide import print_deleted_slides
from .common import require_file
from .edit_operations import EditAction, parse_operation
from .exceptions import PptxError
from .pptx import print_error, print_unexpected_failure

COMMAND = "edit"


@dataclass(frozen=True)
class EditStep:
    """One operation that ran: its 0-based index, its action and the result of its command's core function."""
    index: int
    action: EditAction
    result: object


@dataclass(frozen=True)
class DeckEdited:
    """What `apply_operations` did: the steps in order and the output path."""
    steps: list[EditStep]
    output_path: Path


@dataclass(frozen=True)
class OperationFailure:
    """The operation that failed: its index, its action, the exception, and whether that exception
    came from the command's core function (True) or from parsing the operation (False)."""
    index: int
    action: EditAction
    cause: Exception
    command_ran: bool


class EditError(PptxError):
    """An operation of `edit` failed; nothing was written to the output path.

    `steps` are the operations that ran before it. `failure` is None for an operation that is not
    an object or names no valid action (the message says which).
    """

    def __init__(self, message: str, steps: list[EditStep], failure: OperationFailure | None = None):
        super().__init__(message)
        self.steps = list(steps)
        self.failure = failure


def _action(index: int, spec: object, steps: list[EditStep]) -> EditAction:
    if not isinstance(spec, dict):
        raise EditError(f"Operation {index} is not an object", steps)
    name = spec.get("action")
    try:
        return EditAction(name)
    except ValueError:
        raise EditError(f"Unknown action '{name}'. Valid: {', '.join(sorted(EditAction))}", steps) from None


def apply_operations(input_path: Path, output_path: Path, operations: list) -> DeckEdited:
    """Apply `operations` (spec objects, each with an `action`) in order against `input_path`.

    Each operation is parsed when its turn comes, so the operations before a malformed one run
    first. Writes `output_path` only on success; a failed operation raises EditError.
    """
    if not operations:
        raise PptxError("'operations' list is empty")
    require_file(input_path, f"Input deck not found: {input_path}")

    steps: list[EditStep] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        current = tmp_root / "cur.pptx"
        shutil.copy2(input_path, current)

        for i, spec in enumerate(operations):
            action = _action(i, spec, steps)
            message = f"operation {i} ('{action}') failed"
            try:
                operation = parse_operation(action, spec)
            except Exception as exc:
                raise EditError(message, steps, OperationFailure(i, action, exc, command_ran=False)) from exc
            step_out = tmp_root / f"step-{i}.pptx"
            try:
                result = operation.apply(current, step_out)
            except Exception as exc:
                raise EditError(message, steps, OperationFailure(i, action, exc, command_ran=True)) from exc
            steps.append(EditStep(i, action, result))
            current = step_out

        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
        try:
            shutil.copy2(current, staging)
            staging.replace(output_path)
        except Exception:
            staging.unlink(missing_ok=True)
            raise

    return DeckEdited(steps, output_path)


# --- CLI ---

# Exceptions printed as `Error: <message>` on stderr with no "operation N failed" line.
REPORTED_ERRORS = (ValueError, FileNotFoundError, RuntimeError)


@dataclass(frozen=True)
class ActionPrinters:
    """How the CLI prints one action's step: its command's report, and its command's failure
    printer, which returns False for an exception the command does not print itself."""
    result: Callable[[object], None]
    failure: Callable[[Exception], bool] | None = None


ACTION_PRINTERS: dict[EditAction, ActionPrinters] = {
    EditAction.ADD_TEXT: ActionPrinters(print_text_added, print_add_text_failure),
    EditAction.ADD_TABLE: ActionPrinters(print_tables_added, print_unexpected_failure),
    EditAction.ADD_NOTES: ActionPrinters(print_notes_set, print_unexpected_failure),
    EditAction.ADD_CHART: ActionPrinters(print_chart_added),
    EditAction.ADD_IMAGES: ActionPrinters(print_images_added, print_add_images_failure),
    EditAction.ADD_SLIDE: ActionPrinters(print_added_slides),
    EditAction.COPY_SLIDE: ActionPrinters(print_copied_slides, print_copy_slide_failure),
    EditAction.DELETE_SLIDE: ActionPrinters(print_deleted_slides),
}


def _load_spec(spec_arg: str) -> object:
    """Accept an inline JSON object or array (first character `{` or `[`), else a
    path of any extension, with or without a leading `@`."""
    if spec_arg.lstrip().startswith(("{", "[")):
        return json.loads(spec_arg)
    return json.loads(Path(spec_arg.removeprefix("@")).read_text(encoding="utf-8"))


def _print_step(index: int, action: EditAction) -> None:
    print(f"[{index}] {action}")


def _print_steps(steps: list[EditStep]) -> None:
    for step in steps:
        _print_step(step.index, step.action)
        ACTION_PRINTERS[step.action].result(step.result)


def print_edit_failure(exc: EditError) -> int:
    """Print the steps that ran and the failed operation, and return exit code 1.

    The failed command's error prints as that command prints it, followed by
    `Error: operation N ('action') failed`. An error in parsing the operation, or a
    ValueError, FileNotFoundError or RuntimeError the command does not print, prints
    as `Error: <message>` alone. Any other exception is raised again.
    """
    _print_steps(exc.steps)
    failure = exc.failure
    if failure is None:
        print_error(COMMAND, exc)
        return 1
    _print_step(failure.index, failure.action)
    cause = failure.cause
    print_failure = ACTION_PRINTERS[failure.action].failure
    printed = failure.command_ran and print_failure is not None and print_failure(cause)
    if not printed:
        if isinstance(cause, PptxError):
            print_error(failure.action.value, cause)
        elif isinstance(cause, REPORTED_ERRORS):
            print(f"Error: {cause}", file=sys.stderr)
            return 1
        else:
            raise cause from None
    print_error(COMMAND, exc)
    return 1


def run_edit(args) -> int:
    """Entry point from CLI dispatcher."""
    try:
        spec = _load_spec(args.spec)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read spec: {exc}", file=sys.stderr)
        return 1

    operations = spec.get("operations", spec) if isinstance(spec, dict) else spec
    if not isinstance(operations, list):
        print("Error: spec must be a list of operations, or an object with an "
              "'operations' key", file=sys.stderr)
        return 1

    try:
        result = apply_operations(Path(args.input), Path(args.output), operations)
    except EditError as exc:
        return print_edit_failure(exc)
    except REPORTED_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _print_steps(result.steps)
    print(f"Applied {len(result.steps)} operation(s), saved to: {result.output_path}")
    return 0
