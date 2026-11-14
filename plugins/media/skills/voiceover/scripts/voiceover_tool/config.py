"""Settings and paths for the voiceover CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources. Keys, with the default used when unset:

    VOICEOVER_MODEL_DIR   where model weights are stored (default <plugin data dir>/voiceover)
    VOICEOVER_VOICES_DIR  reference recordings for the chatterbox backend,
                          one `<name>.wav` per voice (default <model dir>/voices)

Model settings, all required by the backend that uses them (no defaults in code):

    VOICEOVER_KOKORO_MODEL_URL   Kokoro ONNX model file URL
    VOICEOVER_KOKORO_VOICES_URL  Kokoro voices file URL
    VOICEOVER_KOKORO_VOICE       default kokoro voice
    VOICEOVER_KOKORO_LANGS       Kokoro voice prefix -> espeak language, comma-separated `prefix=language`
    VOICEOVER_ALIGNER            torchaudio forced-alignment pipeline (`torchaudio.pipelines.<name>`)
    VOICEOVER_ALIGNER_URL        that pipeline's weights file URL
    VOICEOVER_CHATTERBOX_MODEL   Chatterbox model name (label and directory)
    VOICEOVER_CHATTERBOX_URL     base URL of the Chatterbox repository files
    VOICEOVER_CHATTERBOX_FILES   comma-separated file names under that URL
    VOICEOVER_CHATTERBOX_VOICE   default chatterbox voice (`default` is the model's built-in voice)
    VOICEOVER_SPEECH_VOICE       default voice of the configured `speech` model
    VOICEOVER_SPEECH_VOICES      optional, comma-separated voices `voices` lists for the speech backend

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


def require(key: str) -> str:
    """A required setting; exits with an error naming the config file when unset."""
    return PLUGIN.require(key)


def aligner() -> str:
    """The torchaudio forced-alignment pipeline name."""
    return require("VOICEOVER_ALIGNER")


def chatterbox_model() -> str:
    """The Chatterbox model name, also its directory under `model_dir()`."""
    return require("VOICEOVER_CHATTERBOX_MODEL")
