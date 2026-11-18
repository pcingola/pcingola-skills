"""Settings of the music tool.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
The music model (`tasks.music`), the model of `analyze` (`tasks.audio`), the
providers and their keys are in the settings file `config.yaml`.
"""

from __future__ import annotations

import sys

from plugin_settings import Plugin, config, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir


def load_settings() -> None:
    """Load the settings and export them to the process environment (`Plugin.load`); exit when the file is not
    valid. The wrapper path (`__main__`) only: an in-process `cli.main(argv)` calls `check_settings` and leaves
    `os.environ` unchanged."""
    PLUGIN.load()


def check_settings() -> None:
    """Exit when the settings file is not valid (`config()`). Leaves the process environment unchanged."""
    config()


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)
