"""Model routes: the default model of a task and the escalations from it, as Markdown tables
`| task | when | model | why |`.

The default of a task is `models.<task>` of the config file, its one home. The escalation rows come from two
files: the user's `routes.md` in the directory of the config file (`config.path().parent`), then the rows
shipped with this package (`routes.md` beside this module). An escalation's `when` begins with `only when`.
`table` returns, per task, a generated default row, the user's rows, then the shipped rows, without the rows
whose model is not configured: a provider missing from `providers`, or a `diffusers` provider's model missing
from `diffusers`. No code matches `when`; the agent reads it. `command` adds the `routes` command to a skill's CLI.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .errors import AIModelsError, ConfigError

FILE_NAME = "routes.md"
SHIPPED = Path(__file__).with_name(FILE_NAME)
COLUMNS = ("task", "when", "model", "why")
# Every escalation row's `when` starts with this; the generated default row's `when` is DEFAULT.
ESCALATION = "only when"
DEFAULT = "default"
DEFAULT_WHY = "the task's model in config.yaml"


@dataclass(frozen=True)
class Route:
    """One row of a routes table: the model for requests of `task` that `when` describes."""

    task: str
    when: str
    model: str
    why: str


def user_path() -> Path:
    """The user's routes file: `routes.md` in the directory of the config file."""
    return config.path().parent / FILE_NAME


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path: Path) -> list[Route]:
    """The escalation rows of the table in `path` (empty when the file is missing); `ConfigError` naming the
    file and line for a header other than `| task | when | model | why |`, a row of another width, an empty
    cell among task, when and model, a `when` that does not begin with `only when`, or a model that is not
    `<provider>:<model>`."""
    if not path.is_file():
        return []
    rows: list[Route] = []
    header = False
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
        if not (route.task and route.when and route.model):
            raise ConfigError(f"{where}: task, when and model must not be empty")
        if not route.when.lower().startswith(ESCALATION):
            raise ConfigError(f"{where}: `when` must begin with {ESCALATION!r}; the default of a task is "
                              f"`models.{route.task}` of {config.path()}")
        try:
            config.split_id(route.model)
        except ConfigError as e:
            raise ConfigError(f"{where}: {e}") from None
        rows.append(route)
    return rows


def configured(model_id: str, cfg: dict[str, Any]) -> bool:
    """Whether config `cfg` has the provider of `model_id`, and for a `diffusers` provider the model."""
    name, model = config.split_id(model_id)
    spec = (cfg.get("providers") or {}).get(name)
    if not isinstance(spec, dict) or "kind" not in spec:
        return False
    return spec["kind"] != "diffusers" or model in (cfg.get("diffusers") or {})


def table(tasks: Iterable[str]) -> list[Route]:
    """Per task of `tasks`, in order: the default row (`models.<task>`, left out when unset), then the user's
    escalation rows, then the shipped ones, configured models only."""
    cfg = config.load()
    rows = parse(user_path()) + parse(SHIPPED)
    out: list[Route] = []
    for task in tasks:
        default = (cfg.get("models") or {}).get(task)
        if default:
            out.append(Route(task, DEFAULT, str(default), DEFAULT_WHY))
        out += [r for r in rows if r.task == task and configured(r.model, cfg)]
    return out


def markdown(routes: Sequence[Route]) -> str:
    """`routes` as a Markdown table with the header row."""
    lines = [f"| {' | '.join(COLUMNS)} |", "|" + "---|" * len(COLUMNS)]
    lines += [f"| {r.task} | {r.when} | {r.model} | {r.why} |" for r in routes]
    return "\n".join(lines) + "\n"


def command(sub: argparse._SubParsersAction, tasks: Sequence[str]) -> argparse.ArgumentParser:
    """Add `routes [--task T]` to a CLI's subcommands: it prints the table of `tasks` (or of T) and returns
    0, or prints the error and returns 1. The handler is `func` of the parsed arguments."""
    p = sub.add_parser("routes", help="Print the model routes of this skill's tasks: per task the default "
                                      "(models.<task>), then the user's and the shipped escalations")
    p.add_argument("--task", choices=list(tasks), help="only the rows of this task")

    def run(args: argparse.Namespace) -> int:
        try:
            print(markdown(table([args.task] if args.task else tasks)), end="")
        except AIModelsError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0

    p.set_defaults(func=run)
    return p
