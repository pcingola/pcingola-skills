"""Settings and paths for the voiceover CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources. Keys, with the default used when unset:

    VOICEOVER_MODEL_DIR   where model weights are stored (default <plugin data dir>/voiceover)
    VOICEOVER_VOICES_DIR  reference recordings for the chatterbox backend,
                          one `<name>.wav` per voice (default <model dir>/voices)

The `speech` backend's model, provider and key are in the `ai_models` config file.
Weight downloads use httpx's default TLS (it honours SSL_CERT_FILE); the
`speech` backend uses the TLS context of the `ai_models` package.
"""

from __future__ import annotations

import sys
from pathlib import Path

from plugin_settings import Plugin, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def model_dir() -> Path:
    """Directory holding the downloaded weights (outside the plugin)."""
    v = PLUGIN.get("VOICEOVER_MODEL_DIR", "").strip()
    return Path(v).expanduser() if v else plugin_data_dir() / "voiceover"


def voices_dir() -> Path:
    """Directory of cloned-voice reference recordings, `<name>.wav` each."""
    v = PLUGIN.get("VOICEOVER_VOICES_DIR", "").strip()
    return Path(v).expanduser() if v else model_dir() / "voices"
