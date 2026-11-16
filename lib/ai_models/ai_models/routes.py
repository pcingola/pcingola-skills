"""Model routes: per task a default row and the escalations from it, as one Markdown table
`| task | model | when | why |` in the user's `routes.md`, in the directory of the config file
(`config.path().parent`). `setup:settings` creates it from its template.

A row's `when` is `default` (the recommended default model of the task, at most one per task) or begins with
`only when` (an escalation). The model in use is `tasks.<task>` of the config file, its one home: `table` prints
each task's default row with that model, and when it differs from the table's default model, says so in `why`. The
escalation rows follow, without the rows whose model is not configured: a provider missing from `providers`, or a
`diffusers` provider's model missing from its `models`. Without the file, `table` has only the defaults of
`tasks.<task>`. No code matches `when`; the agent reads it. `command` adds the `routes` command to a skill's CLI.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from plugin_settings import Config, ProviderKind

from . import config
from .errors import AIModelsError, ConfigError

FILE_NAME = "routes.md"
COLUMNS = ("task", "model", "when", "why")
# A default row's `when`; every other row's `when` starts with ESCALATION.
DEFAULT = "default"
ESCALATION = "only when"
# The `why` of a default row from `tasks.<task>` when the table has no default row for the task.
DEFAULT_WHY = "set in config.yaml"


@dataclass(frozen=True)
class Route:
    """One row of a routes table: the model for requests of `task` that `when` describes."""

    task: str
    model: str
    when: str
    why: str

    @property
    def is_default(self) -> bool:
        return self.when.lower() == DEFAULT



def user_path() -> Path:
    """The user's routes file: `routes.md` in the directory of the config file."""
    return config.path().parent / FILE_NAME


def missing_message(path: Path) -> str:
    """The note `command` prints when the routes file `path` is missing."""
    return (f"no routes table at {path}; the default rows are tasks.<task> of config.yaml only. "
            "The setup:settings skill creates the table.")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path: Path) -> list[Route]:
    """The rows of the table in `path` (empty when the file is missing); `ConfigError` naming the file and line
    for a header other than `| task | model | when | why |`, a row of another width, an empty cell among task,
    model and when, a `when` that is neither `default` nor begins with `only when`, a second default row of a
    task, or a model that is not `<provider>:<model>`."""
    if not path.is_file():
        return []
    rows: list[Route] = []
    header = False
    defaults: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        where = f"{path}:{n}"
        if not header:
            if tuple(c.lower() for c in cells) != COLUMNS:
                raise ConfigError(f"{where}: the table header must be | {' | '.join(COLUMNS)} |")
            header = True
            continue
        if all(c and set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) != len(COLUMNS):
            raise ConfigError(f"{where}: a row has {len(COLUMNS)} cells ({', '.join(COLUMNS)}), not {len(cells)}")
        route = Route(*cells)
        if not (route.task and route.model and route.when):
            raise ConfigError(f"{where}: task, model and when must not be empty")
        if route.is_default:
            if route.task in defaults:
                raise ConfigError(f"{where}: a second {DEFAULT!r} row of task {route.task}")
            defaults.add(route.task)
        elif not route.when.lower().startswith(ESCALATION):
            raise ConfigError(f"{where}: `when` must be {DEFAULT!r} or begin with {ESCALATION!r}")
        try:
            config.split_id(route.model)
        except ConfigError as e:
            raise ConfigError(f"{where}: {e}") from None
        rows.append(route)
    return rows


def configured(model_id: str, cfg: Config) -> bool:
    """Whether config `cfg` has the provider of `model_id`, and for a `diffusers` provider the model's entry."""
    name, model = config.split_id(model_id)
    spec = cfg.provider(name)
    if spec is None:
        return False
    return spec.kind != ProviderKind.DIFFUSERS or model in spec.models


def _default(task: str, recommended: Route | None, cfg: Config) -> Route | None:
    """The default row of `task`: the model of `tasks.<task>` (none when unset), with the table's `why` when the
    models agree and the table's recommendation when they differ."""
    model = cfg.task_model(task)
    if not model:
        return None
    if recommended is None:
        return Route(task, model, DEFAULT, DEFAULT_WHY)
    if recommended.model == model:
        return Route(task, model, DEFAULT, recommended.why)
    return Route(task, model, DEFAULT,
                 f"{DEFAULT_WHY}; the table recommends {recommended.model}: {recommended.why}")


def table(tasks: Iterable[str]) -> list[Route]:
    """Per task of `tasks`, in order: the default row (`_default`), then the table's escalation rows,
    configured models only."""
    cfg = config.load()
    rows = parse(user_path())
    out: list[Route] = []
    for task in tasks:
        mine = [r for r in rows if r.task == task]
        default = _default(task, next((r for r in mine if r.is_default), None), cfg)
        if default:
            out.append(default)
        out += [r for r in mine if not r.is_default and configured(r.model, cfg)]
    return out


def markdown(routes: Sequence[Route]) -> str:
    """`routes` as a Markdown table with the header row."""
    lines = [f"| {' | '.join(COLUMNS)} |", "|" + "---|" * len(COLUMNS)]
    lines += [f"| {r.task} | {r.model} | {r.when} | {r.why} |" for r in routes]
    return "\n".join(lines) + "\n"


def command(sub: argparse._SubParsersAction, tasks: Sequence[str]) -> argparse.ArgumentParser:
    """Add `routes [--task T]` to a CLI's subcommands: it prints the table of `tasks` (or of T), and the note of
    `missing_message` on stderr when the user's file is missing, and returns 0; or prints the error and returns 1.
    The handler is `func` of the parsed arguments."""
    p = sub.add_parser("routes", help="Print the model routes of this skill's tasks from routes.md beside "
                                      "config.yaml: per task the default row (tasks.<task>), then the escalations")
    p.add_argument("--task", choices=list(tasks), help="only the rows of this task")

    def run(args: argparse.Namespace) -> int:
        try:
            print(markdown(table([args.task] if args.task else tasks)), end="")
            if not user_path().is_file():
                print(missing_message(user_path()), file=sys.stderr)
        except AIModelsError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0

    p.set_defaults(func=run)
    return p
