"""Kokoro (provider kind `kokoro`): local speech with kokoro-onnx on the CPU, in the caller's process (extra
`ai-models[kokoro]`).

A model entry (`providers.<p>.models.<m>`, `KokoroModel`) names the model files (`model_url`, `voices_url`),
downloaded to `weights.model_dir`, and the espeak-ng language of each voice-name prefix (`langs`, a mapping such as
`af_: en-us`). A voice whose name has
no listed prefix is refused, and `voices` lists only the voices of the listed prefixes. The model takes no
instructions; the speed is 0.5 to 2. The audio is a 24 kHz WAV file. The model stays loaded for the life of the
process or until `local.unload_model` drops it; it needs no GPU and no local-model lock. A load of a model whose
entry sets `memory` is refused when the system's available memory is below it (`local.check_free`).

Cancellation: a cancel signal (`cancel.signal`) is checked before `Kokoro.create` only; kokoro-onnx synthesizes its
batches without returning to the caller, so a synthesis that has started runs to its end.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from plugin_settings import KokoroModel, KokoroProvider, ProviderKind

from . import cancel, config, espeak, local, weights
from .errors import AIModelsError

KIND = ProviderKind.KOKORO
SAMPLE_RATE = 24_000

_models: dict[Path, Any] = {}
_lock = threading.Lock()  # one load at a time when callers run in several threads
local.on_unload(_models)


@local.on_unload_model
def _drop(model_id: str, weights_dir: Path | None) -> int:
    """Drop the loaded kokoro model `model_id`, whose files are in its provider's `dir`, else in `weights_dir`."""
    if not _models or local.provider_kind(model_id) != KIND:
        return 0
    name, bare = config.split_id(model_id)
    d = weights.model_dir(config.provider(name).with_dir(weights_dir), bare)
    keys = [k for k in _models if k.parent == d]
    for k in keys:
        del _models[k]
    return len(keys)


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
        if entry.memory is not None:
            local.check_free(entry.memory, str(onnx), f"the entry of {bare}", "cpu", False)
        from kokoro_onnx import EspeakConfig, Kokoro

        _models[onnx] = Kokoro(str(onnx), str(voices_file),
                               espeak_config=EspeakConfig(data_path=espeak.data_path(weights.root(spec))))
    return _models[onnx]


def voices(spec: KokoroProvider, entry: KokoroModel, name: str, bare: str) -> list[str]:
    """The voices of the model whose prefix is in `langs`, sorted, read from its voices file (a NumPy archive with
    one array per voice, which kokoro-onnx loads with `np.load`); the model file is neither downloaded nor loaded."""
    import numpy as np

    path = weights.ensure_file(entry.voices_url, weights.model_dir(spec, bare) / weights.basename(entry.voices_url))
    prefixes = tuple(entry.langs)
    with np.load(path) as archive:
        return sorted(v for v in archive.files if v.startswith(prefixes))


def speak(spec: KokoroProvider, entry: KokoroModel, name: str, bare: str, text: str, voice: str,
          speed: float) -> bytes:
    """A 24 kHz WAV file of `text` in `voice`."""
    from .speech import float_wav

    language = lang(entry, f"{name}:{bare}", voice)
    k = model(spec, entry, bare)
    if voice not in k.get_voices():
        raise AIModelsError(f"{name}:{bare} has no voice {voice!r}; `voices` lists them")
    cancel.check()
    samples, rate = k.create(text, voice=voice, speed=speed, lang=language)
    return float_wav(samples, rate)
