"""Kokoro (provider kind `kokoro`): local speech with kokoro-onnx on the CPU, in the caller's process (extra
`ai-models[kokoro]`).

A model entry (`providers.<p>.models.<m>`, `KokoroModel`) names the model files (`model_url`, `voices_url`),
downloaded to `weights.model_dir`, and the espeak-ng language of each voice-name prefix (`langs`, a mapping such as
`af_: en-us`). A voice whose name has
no listed prefix is refused, and `voices` lists only the voices of the listed prefixes. The model takes no
instructions; the speed is 0.5 to 2. The audio is a 24 kHz WAV file. The model stays loaded for the life of the
process; it needs no GPU and no local-model lock.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from plugin_settings import KokoroModel, KokoroProvider, ProviderKind

from . import espeak, local, weights
from .errors import AIModelsError

KIND = ProviderKind.KOKORO
SAMPLE_RATE = 24_000

_models: dict[Path, Any] = {}
_lock = threading.Lock()  # one load at a time when callers run in several threads
local.on_unload(_models)


def files(spec: KokoroProvider, entry: KokoroModel, model: str) -> tuple[Path, Path]:
    """The model and voices files of the provider's `model`, downloaded when missing."""
    d = weights.model_dir(spec, model)
    return tuple(weights.ensure_file(url, d / weights.basename(url)) for url in (entry.model_url, entry.voices_url))


def lang(entry: KokoroModel, model_id: str, voice: str) -> str:
    """The espeak-ng language of `voice`, from the model's `langs` (voice-name prefix to language)."""
    for prefix, language in entry.langs.items():
        if voice.startswith(prefix):
            return language
    raise AIModelsError(f"{model_id}: voice {voice!r} has no language in the model's `langs` "
                        f"({', '.join(entry.langs)})")


def model(spec: KokoroProvider, entry: KokoroModel, bare: str):
    """The loaded `kokoro_onnx.Kokoro` of model `bare`, one per model file per process."""
    with _lock:
        return _load(spec, entry, bare)


def _load(spec: KokoroProvider, entry: KokoroModel, bare: str):
    onnx, voices_file = files(spec, entry, bare)
    if onnx not in _models:
        from kokoro_onnx import EspeakConfig, Kokoro

        _models[onnx] = Kokoro(str(onnx), str(voices_file),
                               espeak_config=EspeakConfig(data_path=espeak.data_path(weights.root(spec))))
    return _models[onnx]


def voices(spec: KokoroProvider, entry: KokoroModel, name: str, bare: str) -> list[str]:
    """The voices of the model whose prefix is in `langs`."""
    prefixes = tuple(entry.langs)
    return [v for v in model(spec, entry, bare).get_voices() if v.startswith(prefixes)]


def speak(spec: KokoroProvider, entry: KokoroModel, name: str, bare: str, text: str, voice: str,
          speed: float) -> bytes:
    """A 24 kHz WAV file of `text` in `voice`."""
    from .speech import float_wav

    language = lang(entry, f"{name}:{bare}", voice)
    k = model(spec, entry, bare)
    if voice not in k.get_voices():
        raise AIModelsError(f"{name}:{bare} has no voice {voice!r}; `voices` lists them")
    samples, rate = k.create(text, voice=voice, speed=speed, lang=language)
    return float_wav(samples, rate)
