"""TTS backends behind one interface.

A backend turns one sentence into mono float32 samples at `sample_rate`.
Register new backends in `BACKENDS` (name -> factory taking `style`).

- `kokoro`: local Kokoro v1.0 (kokoro-onnx), English voices only, no style.
- `chatterbox`: local Chatterbox-Turbo with voice cloning, see `chatterbox.py`.
- `speech`: the `speech` model of the `ai_models` config (OpenAI-style, Gemini
  TTS or Ollama), see `speech.py`.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

import numpy as np

from . import download


@runtime_checkable
class TTSBackend(Protocol):
    name: str
    sample_rate: int
    default_voice: str

    def voices(self) -> list[str]: ...

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        """Return mono float32 samples in [-1, 1] at `self.sample_rate`."""
        ...


# Kokoro voice prefix -> espeak language: American (a) and British (b) English
KOKORO_LANGS = {"af_": "en-us", "am_": "en-us", "bf_": "en-gb", "bm_": "en-gb"}


def kokoro_lang(voice: str) -> str:
    for prefix, lang in KOKORO_LANGS.items():
        if voice.startswith(prefix):
            return lang
    raise ValueError(f"kokoro voice {voice!r} is not an English voice; run `voiceover.sh voices`")


class KokoroBackend:
    """Kokoro v1.0 via kokoro-onnx, weights from the project's GitHub release."""

    name = "kokoro"
    sample_rate = 24_000
    default_voice = "af_heart"

    def __init__(self, style: str | None = None) -> None:
        if style:
            raise ValueError("kokoro takes no style; use the speech backend for --style")
        self._kokoro = None

    def _model(self):
        if self._kokoro is None:
            from kokoro_onnx import EspeakConfig, Kokoro

            from . import espeak

            model = download.ensure_weight(download.KOKORO_MODEL)
            voices = download.ensure_weight(download.KOKORO_VOICES)
            config = EspeakConfig(data_path=espeak.data_path())
            self._kokoro = Kokoro(str(model), str(voices), espeak_config=config)
        return self._kokoro

    def voices(self) -> list[str]:
        return [v for v in self._model().get_voices() if v.startswith(tuple(KOKORO_LANGS))]

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        lang = kokoro_lang(voice)
        samples, sr = self._model().create(text, voice=voice, speed=speed, lang=lang)
        if sr != self.sample_rate:
            raise RuntimeError(f"kokoro returned {sr} Hz, expected {self.sample_rate} Hz")
        return np.asarray(samples, dtype=np.float32).reshape(-1)


def _speech(style: str | None = None) -> TTSBackend:
    from .speech import SpeechBackend

    return SpeechBackend(style)


def _chatterbox(style: str | None = None) -> TTSBackend:
    from .chatterbox import ChatterboxBackend

    return ChatterboxBackend(style)


BACKENDS: dict[str, Callable[..., TTSBackend]] = {
    "kokoro": KokoroBackend,
    "chatterbox": _chatterbox,
    "speech": _speech,
}
DEFAULT_BACKEND = "kokoro"


def get_backend(name: str, style: str | None = None) -> TTSBackend:
    try:
        factory = BACKENDS[name]
    except KeyError:
        raise ValueError(f"unknown backend {name!r}; available: {', '.join(sorted(BACKENDS))}") from None
    return factory(style)
