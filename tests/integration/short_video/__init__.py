"""Helpers for short_video tests: `cli` runs the short-video CLI in process."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


@dataclass(frozen=True)
class CliResult:
    """Exit code and captured output of one in-process CLI call."""

    returncode: int
    stdout: str
    stderr: str


def cli(*argv: str) -> CliResult:
    """Run the short-video CLI's `main(argv)` in process with the plugin environment directory of the wrapper
    (`wrapper_env.ENV_DIR`), capturing stdout and stderr.

    For tests whose subject is CLI behaviour: argument parsing, the printed output an agent reads and the exit code.
    Tests of a command's logic call its module function instead. Settings come from the file set with
    `tests.settings_env.use_settings`.
    """
    from short_video_tool.cli import main

    from .wrapper_env import ENV_DIR

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv), plugin_env_dir=ENV_DIR)
    return CliResult(code, out.getvalue(), err.getvalue())
