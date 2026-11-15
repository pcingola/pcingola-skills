"""Settings and paths for the voiceover CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources. The one key, with the
default used when unset:

    VOICEOVER_VOICES_DIR  reference recordings of `add-voice`, `<name>.<suffix>` each, with an optional transcript
                          `<name>.txt` (default <plugin data dir>/voiceover/voices)

The speech and align models, their providers, weights and default voices are in the `ai_models` config
(`models.speech`, `models.align`).
"""

from __future__ import annotations

from pathlib import Path

from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load


def voices_dir() -> Path:
    """Directory of the reference recordings, `<name>.<suffix>` each."""
    v = PLUGIN.get("VOICEOVER_VOICES_DIR", "").strip()
    return Path(v).expanduser() if v else plugin_data_dir() / "voiceover" / "voices"
