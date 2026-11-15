"""Settings and paths for the voiceover CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources. The one key, with the
default used when unset:

    VOICEOVER_VOICES_DIR  reference recordings of `add-voice`, `<name>.<suffix>` each, with an optional transcript
                          `<name>.txt` (default <plugin data dir>/voiceover/voices)

The speech and align models, their providers, weights and default voices are in the `ai_models` config
(`models.speech`, `models.align`). `load_settings` refuses every other `VOICEOVER_*` setting of the file (the
model settings of an earlier version), naming the entries that replace them.
"""

from __future__ import annotations

from pathlib import Path

import plugin_settings
from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
PREFIX = "VOICEOVER_"
VOICES_KEY = "VOICEOVER_VOICES_DIR"
MODEL_DIR_KEY = "VOICEOVER_MODEL_DIR"  # the weights and voices directory of an earlier version


def obsolete_message(keys: list[str], model_dir: str | None) -> str:
    """The refusal of the earlier `VOICEOVER_*` model settings `keys`; `model_dir` is VOICEOVER_MODEL_DIR's value."""
    msg = (f"settings {', '.join(keys)} in {plugin_settings.config_file()} are no longer read: the speech and align "
           "models are config.yaml models. Copy the provider entries `kokoro` and `torchaudio` (and `chatterbox` "
           "for cloned voices) and `models.speech` and `models.align` of the setup:settings template "
           "(config.example.yaml) into config.yaml, then delete these settings.")
    if model_dir:
        msg += (f" The weights now default to {plugin_data_dir() / 'voiceover'}; to keep them in {model_dir}, give "
                f"those provider entries `dir: {model_dir}`, and when it holds voices/, set "
                f"{VOICES_KEY}: {model_dir}/voices.")
    return msg


def load_settings() -> None:
    """Load the settings (`Plugin.load`); exit when the file sets a `VOICEOVER_*` key other than VOICEOVER_VOICES_DIR."""
    PLUGIN.load()
    s = plugin_settings.settings()
    old = sorted(k for k in s if k.startswith(PREFIX) and k != VOICES_KEY)
    if old:
        error(obsolete_message(old, s.get(MODEL_DIR_KEY)))


def voices_dir() -> Path:
    """Directory of the reference recordings, `<name>.<suffix>` each."""
    v = PLUGIN.get("VOICEOVER_VOICES_DIR", "").strip()
    return Path(v).expanduser() if v else plugin_data_dir() / "voiceover" / "voices"
