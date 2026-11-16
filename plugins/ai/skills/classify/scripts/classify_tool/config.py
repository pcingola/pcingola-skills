"""Settings of the classify tool, loaded by `plugin_settings` (`Plugin.load`), which
documents the file. The models are those of `config.yaml` (`tasks.system1`,
`tasks.chat`), with the provider keys."""

from __future__ import annotations

from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load

DEFAULT_CONCURRENCY = 4
DEFAULT_RETRY_FAILED = 2
