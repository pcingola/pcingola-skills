"""Helpers for voiceover unit tests: `voiceover` runs the voiceover CLI in process."""

from pathlib import Path

from tests.inproc import CliResult, run_main


def voiceover(*argv: str, config: Path) -> CliResult:
    """`voiceover_tool.cli.main(argv)` in process with the settings file `config`, capturing stdout and stderr."""
    from voiceover_tool.cli import main

    return run_main(main, *argv, settings=config)
