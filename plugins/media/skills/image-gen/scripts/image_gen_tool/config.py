"""Settings of the image-gen CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
The model of each task (`tasks.image`, `tasks.image_edit`, `tasks.image_best`, `tasks.image_multi_ref`), the
providers, their keys and each model's image limits are in the settings file `config.yaml`.
"""

from __future__ import annotations

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
