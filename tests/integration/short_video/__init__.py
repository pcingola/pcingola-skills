"""Helpers for short_video tests: `cli` runs the short-video CLI in process."""

from __future__ import annotations

from functools import partial

from tests.inproc import CliResult, run_main


def cli(*argv: str) -> CliResult:
    """Run the short-video CLI's `main(argv)` in process with the plugin environment directory of the wrapper
    (`wrapper_env.ENV_DIR`), capturing stdout and stderr (`tests.inproc.run_main`).

    For tests whose subject is CLI behaviour: argument parsing, the printed output an agent reads and the exit code.
    Tests of a command's logic call its module function instead. Settings come from the file set with
    `tests.settings_env.use_settings`.
    """
    from short_video_tool.cli import main

    from .wrapper_env import ENV_DIR

    return run_main(partial(main, plugin_env_dir=ENV_DIR), *argv)
