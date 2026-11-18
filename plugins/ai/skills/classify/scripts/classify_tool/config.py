"""Settings of the classify tool, loaded by `plugin_settings` (`Plugin.load`), which
documents the file. The models are those of `config.yaml` (`tasks.system1`,
`tasks.chat`), with the provider keys."""

from __future__ import annotations

from plugin_settings import Plugin, config, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir

DEFAULT_CONCURRENCY = 4
DEFAULT_RETRY_FAILED = 2


def load_settings() -> None:
    """Load the settings and export them to the process environment (`Plugin.load`); exit when the file is not
    valid. The wrapper path (`__main__`) only: an in-process `cli.main(argv)` calls `check_settings` and leaves
    `os.environ` unchanged."""
    PLUGIN.load()


def check_settings() -> None:
    """Exit when the settings file is not valid (`config()`). Leaves the process environment unchanged."""
    config()
