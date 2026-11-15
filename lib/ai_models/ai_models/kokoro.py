"""Kokoro (provider kind `kokoro`): local speech with kokoro-onnx on the CPU, in the caller's process (extra
`ai-models[kokoro]`).

A provider entry names the model files (`model_url`, `voices_url`), downloaded to `weights.model_dir`, and the
espeak-ng language of each voice-name prefix (`langs`, a mapping such as `af_: en-us`). A voice whose name has
no listed prefix is refused, and `voices` lists only the voices of the listed prefixes. The model takes no
instructions; the speed is 0.5 to 2. The audio is a 24 kHz WAV file. The model stays loaded for the life of the
process; it needs no GPU and no local-model lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import espeak, weights
from .config import required
from .errors import AIModelsError, ConfigError

KIND = "kokoro"
SAMPLE_RATE = 24_000

_models: dict[Path, Any] = {}


def files(spec: dict[str, Any], name: str, model: str) -> tuple[Path, Path]:
    """The model and voices files of provider `name`'s `model`, downloaded when missing."""
    urls = (str(required(spec, "model_url", name)), str(required(spec, "voices_url", name)))
    d = weights.model_dir(spec, model)
    return tuple(weights.ensure_file(url, d / weights.basename(url)) for url in urls)


def langs(spec: dict[str, Any], name: str) -> dict[str, str]:
    """Voice-name prefix to espeak-ng language, from the provider's `langs` mapping."""
    m = required(spec, "langs", name)
    if not isinstance(m, dict) or not all(str(k) and str(v) for k, v in m.items()):
        raise ConfigError(f"provider {name!r}: `langs` must map voice-name prefixes to espeak languages "
                          "({af_: en-us, ...})")
    return {str(k): str(v) for k, v in m.items()}


def lang(spec: dict[str, Any], name: str, voice: str) -> str:
    for prefix, language in langs(spec, name).items():
        if voice.startswith(prefix):
            return language
    raise AIModelsError(f"{name}: voice {voice!r} has no language in the provider's `langs` "
                        f"({', '.join(langs(spec, name))})")


def model(spec: dict[str, Any], name: str, bare: str):
    """The loaded `kokoro_onnx.Kokoro` of provider `name`'s model `bare`, one per model file per process."""
    onnx, voices_file = files(spec, name, bare)
    if onnx not in _models:
        from kokoro_onnx import EspeakConfig, Kokoro

        _models[onnx] = Kokoro(str(onnx), str(voices_file),
                               espeak_config=EspeakConfig(data_path=espeak.data_path(weights.root(spec))))
    return _models[onnx]


def voices(spec: dict[str, Any], name: str, bare: str) -> list[str]:
    """The voices of the model whose prefix is in `langs`."""
    prefixes = tuple(langs(spec, name))
    return [v for v in model(spec, name, bare).get_voices() if v.startswith(prefixes)]


def speak(spec: dict[str, Any], name: str, bare: str, text: str, voice: str, speed: float) -> bytes:
    """A 24 kHz WAV file of `text` in `voice`."""
    import numpy as np

    from .speech import wav

    language = lang(spec, name, voice)
    k = model(spec, name, bare)
    if voice not in k.get_voices():
        raise AIModelsError(f"{name}:{bare} has no voice {voice!r}; `voices` lists them")
    samples, rate = k.create(text, voice=voice, speed=speed, lang=language)
    pcm = (np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767).astype("<i2")
    return wav(pcm.tobytes(), int(rate))
