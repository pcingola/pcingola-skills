"""Apply a sequence of operations to a deck in one call, atomically.

`edit` runs the same code the individual commands run — each action dispatches
straight to that command's runner. It buys two things a shell chain of separate
invocations cannot:

- **No temp files to thread.** Nine operations used to mean nine intermediate
  decks and nine paths to keep straight.
- **Atomicity.** Every step writes inside a temporary directory; the output path
  is only touched at the end, by `Path.replace`, which is atomic on the same
  filesystem. A failure at step 7 of 9 leaves no half-written deck behind — not a
  truncated file, not a stale one, nothing.

Every action name is the name of a command. `add-text` runs `add-text`. There is
no separate action vocabulary to keep in sync with the CLI.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .cmd_add_chart import run_add_chart
from .cmd_add_images import run_add_images
from .cmd_add_notes import run_add_notes
from .cmd_add_slide import add_slides_to_file
from .cmd_add_table import run_add_table
from .cmd_add_text import run_add_text
from .cmd_copy_slide import run_copy_slide
from .cmd_delete_slide import run_delete_slide


def _load_spec(spec_arg: str) -> object:
    """Accept an inline JSON object or array (first character `{` or `[`), else a
    path of any extension, with or without a leading `@`."""
    if spec_arg.lstrip().startswith(("{", "[")):
        return json.loads(spec_arg)
    return json.loads(Path(spec_arg.removeprefix("@")).read_text(encoding="utf-8"))


def _write_tmp_json(data: object, tmp_root: Path, name: str) -> Path:
    path = tmp_root / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _require(op: dict, key: str, action: str):
    if key not in op:
        raise ValueError(f"'{action}' operation requires '{key}'")
    return op[key]


def _slide_keyed(op: dict, action: str) -> dict:
    """Return the operation's `data` in the slide-N-keyed form the commands take.

    Accepts either that form directly, or a bare per-slide payload plus a
    `slide` index — the shorthand is what most callers reach for when the whole
    operation targets one slide.
    """
    data = _require(op, "data", action)
    if isinstance(data, dict) and any(str(k).startswith("slide-") for k in data):
        return data
    slide = _require(op, "slide", action)
    return {f"slide-{int(slide)}": data}


def _run_add_text(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    data_path = _write_tmp_json(_slide_keyed(op, "add-text"), tmp_root, f"text-{i}.json")
    run_add_text(argparse.Namespace(input=str(current), text_data=str(data_path), output=str(out)))


def _run_add_table(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    data_path = _write_tmp_json(_slide_keyed(op, "add-table"), tmp_root, f"table-{i}.json")
    run_add_table(argparse.Namespace(input=str(current), table_data=str(data_path), output=str(out)))


def _run_add_notes(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    data_path = _write_tmp_json(_slide_keyed(op, "add-notes"), tmp_root, f"notes-{i}.json")
    run_add_notes(argparse.Namespace(input=str(current), notes_data=str(data_path), output=str(out)))


def _run_add_chart(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    data_path = _write_tmp_json(_require(op, "data", "add-chart"), tmp_root, f"chart-{i}.json")
    run_add_chart(argparse.Namespace(
        input=str(current), output=str(out),
        slide=int(_require(op, "slide", "add-chart")),
        chart_data=str(data_path), index=int(op.get("index", 0)),
    ))


def _run_add_images(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    images = op.get("images", op.get("image"))
    if images is None:
        raise ValueError("'add-images' operation requires 'images'")
    if isinstance(images, list):
        images = ",".join(str(p) for p in images)
    run_add_images(argparse.Namespace(
        input=str(current), output=str(out),
        slide=int(_require(op, "slide", "add-images")),
        images=str(images),
        placeholder_type=op.get("type", "PICTURE"),
        index=op.get("index"),
    ))


def _run_copy_slide(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    """Copy slides from another deck into this one. The current deck is the target."""
    indices = _require(op, "source_indices", "copy-slide")
    if isinstance(indices, (list, tuple)):
        indices = ",".join(str(x) for x in indices)
    position = op.get("position")
    run_copy_slide(argparse.Namespace(
        source=str(_require(op, "source", "copy-slide")),
        target=str(current), output=str(out),
        source_indices=str(indices),
        position=None if position is None else int(position),
    ))


def _run_add_slide(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    layouts = _require(op, "layouts", "add-slide")
    if isinstance(layouts, (list, tuple)):
        names = [str(x) for x in layouts]
    else:
        names = [n.strip() for n in str(layouts).split(",") if n.strip()]
    position = op.get("position")
    add_slides_to_file(current, out, names, None if position is None else int(position))


def _run_delete_slide(op: dict, current: Path, out: Path, tmp_root: Path, i: int) -> None:
    indices = op.get("indices", op.get("slide"))
    if indices is None:
        raise ValueError("'delete-slide' operation requires 'indices'")
    if isinstance(indices, (list, tuple)):
        indices = ",".join(str(x) for x in indices)
    run_delete_slide(argparse.Namespace(
        input=str(current), output=str(out), indices=str(indices)))


ACTION_RUNNERS = {
    "add-text": _run_add_text,
    "add-table": _run_add_table,
    "add-notes": _run_add_notes,
    "add-chart": _run_add_chart,
    "add-images": _run_add_images,
    "add-slide": _run_add_slide,
    "copy-slide": _run_copy_slide,
    "delete-slide": _run_delete_slide,
}


def apply_operations(input_path: Path, output_path: Path, operations: list[dict]) -> None:
    """Apply `operations` in order against `input_path`. Writes `output_path` only on success."""
    if not operations:
        raise ValueError("'operations' list is empty")
    if not input_path.exists():
        raise FileNotFoundError(f"Input deck not found: {input_path}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        current = tmp_root / "cur.pptx"
        shutil.copy2(input_path, current)

        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                raise ValueError(f"Operation {i} is not an object")
            action = op.get("action")
            runner = ACTION_RUNNERS.get(action)
            if runner is None:
                raise ValueError(
                    f"Unknown action '{action}'. Valid: {', '.join(sorted(ACTION_RUNNERS))}"
                )
            step_out = tmp_root / f"step-{i}.pptx"
            print(f"[{i}] {action}")
            try:
                runner(op, current, step_out, tmp_root, i)
            except SystemExit as exc:
                # The commands exit(1) on their own errors. Inside `edit` that is
                # a failed step, not a failed process — say which one and abort
                # before anything reaches output_path.
                if exc.code:
                    raise RuntimeError(f"operation {i} ('{action}') failed") from None
            if not step_out.exists():
                raise RuntimeError(f"operation {i} ('{action}') produced no output file")
            current = step_out

        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
        try:
            shutil.copy2(current, staging)
            staging.replace(output_path)
        except Exception:
            staging.unlink(missing_ok=True)
            raise

    print(f"Applied {len(operations)} operation(s), saved to: {output_path}")


def run_edit(args) -> None:
    """Entry point from CLI dispatcher."""
    try:
        spec = _load_spec(args.spec)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read spec: {exc}", file=sys.stderr)
        sys.exit(1)

    operations = spec.get("operations", spec) if isinstance(spec, dict) else spec
    if not isinstance(operations, list):
        print("Error: spec must be a list of operations, or an object with an "
              "'operations' key", file=sys.stderr)
        sys.exit(1)

    try:
        apply_operations(Path(args.input), Path(args.output), operations)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
