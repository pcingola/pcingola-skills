"""Settings of the music tool.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
The music model (task `music`), the model of `analyze` (task `audio`), the
providers and their keys are in the settings file `config.yaml`.
"""

from __future__ import annotations

import sys

from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load
require = PLUGIN.require


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)
