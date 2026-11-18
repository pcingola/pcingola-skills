"""Run a skill CLI's `main(argv) -> int` in process, with an optional settings file, capturing its output.

For tests whose subject is CLI behaviour: argument parsing, the printed output an agent reads and the exit code.
Tests of a command's work call its module function instead."""
from __future__ import annotations

import contextlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tests.settings_env import use_settings


@dataclass(frozen=True)
class CliResult:
    """Exit code and captured output of one in-process CLI call."""

    returncode: int
    stdout: str
    stderr: str


def run_main(main: Callable[[list[str]], int], *argv: str, settings: Path | None = None) -> CliResult:
    """`main(list(argv))` with stdout and stderr captured; with `settings`, the settings file inside the call
    (`use_settings`), else the one already set."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if settings is not None:
            stack.enter_context(use_settings(settings))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
    return CliResult(code, out.getvalue(), err.getvalue())
