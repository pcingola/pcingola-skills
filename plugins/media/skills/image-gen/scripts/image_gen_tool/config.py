"""Settings of the image-gen CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
The model of each task (`tasks.image`, `tasks.image_edit`, `tasks.image_best`, `tasks.image_multi_ref`), the
providers, their keys and each model's image limits are in the settings file `config.yaml`.
"""

from __future__ import annotations

from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load
