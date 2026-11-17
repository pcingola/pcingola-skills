"""Chatterbox Turbo (provider kind `chatterbox`): local speech with zero-shot voice cloning, on the CPU, in the
caller's process (extra `ai-models[chatterbox]`).

A model entry (`providers.<p>.models.<m>`, `ChatterboxModel`) names its files, `files` under the repository URL
`url`, downloaded to `weights.model_dir`. The model is loaded once per weights directory and stays loaded for the life
of the process (`local.unload` drops it); it needs no GPU and no local-model lock. One synthesis runs at a time
(`_lock`), because the loaded model holds the conditioning of one voice, on the fast cores of the CPU
(`cpu.performance_threads`).

A voice is `default` (the model's built-in voice) or the path of a reference recording longer than
`MIN_REFERENCE_SECONDS`; the model uses its first 10 to 15 s and copies the speaker and also the delivery,
microphone and room. The output is a 24 kHz WAV file with Resemble's Perth watermark (inaudible). There is no speed
or style control.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugin_settings import ChatterboxModel, ChatterboxProvider, ProviderKind

from . import cpu, local, weights
from .errors import AIModelsError

KIND = ProviderKind.CHATTERBOX
DEFAULT_VOICE = "default"
DEVICE = "cpu"
MIN_REFERENCE_SECONDS = 5.0
SAMPLE_RATE = 24_000


@dataclass
class Loaded:
    """A loaded model: `tts` (`ChatterboxTurboTTS`), the conditioning of its built-in voice, and the reference
    recording whose conditioning `tts` holds now (None: the built-in voice)."""

    tts: Any
    builtin: Any
    reference: str | None = None


_models: dict[Path, Loaded] = {}
_lock = threading.Lock()  # one load or synthesis at a time when callers run in several threads
local.on_unload(_models.clear)


def fetch(spec: ChatterboxProvider, entry: ChatterboxModel, model: str) -> Path:
    """The directory of the model files, each downloaded when missing."""
    base = entry.url.rstrip("/")
    d = weights.model_dir(spec, model)
    for f in entry.files:
        weights.ensure_file(f"{base}/{f}", d / f)
    return d


def _load(spec: ChatterboxProvider, entry: ChatterboxModel, model: str) -> Loaded:
    """The loaded model of provider `spec`'s `model`, loaded on the first call; the caller holds `_lock`."""
    d = fetch(spec, entry, model)
    if d not in _models:
        import numpy as np
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        tts = ChatterboxTurboTTS.from_local(str(d), DEVICE)
        # Under numpy 2 the loudness gain (a float64 scalar) promotes the float32 reference to float64, which the
        # mel filter matmul rejects.
        norm = tts.norm_loudness
        tts.norm_loudness = lambda wav, sr, target_lufs=-27: np.asarray(norm(wav, sr, target_lufs), dtype=np.float32)
        _models[d] = Loaded(tts, tts.conds)
    return _models[d]


def reference(voice: str) -> str | None:
    """The recording path of `voice`, None for `DEFAULT_VOICE`."""
    if voice == DEFAULT_VOICE:
        return None
    p = Path(voice).expanduser()
    if not p.is_file():
        raise AIModelsError(f"voice {voice!r} is neither {DEFAULT_VOICE!r} nor a reference recording (a file)")
    return str(p.resolve())


def check_reference(path: str) -> None:
    """`AIModelsError` when the recording at `path` is unreadable or not longer than `MIN_REFERENCE_SECONDS`."""
    import soundfile as sf

    try:
        seconds = sf.info(path).duration
    except (RuntimeError, OSError) as e:
        raise AIModelsError(f"{path}: not a readable recording: {e}") from e
    if seconds <= MIN_REFERENCE_SECONDS:
        raise AIModelsError(f"{path}: {seconds:.1f} s; a reference must be longer than {MIN_REFERENCE_SECONDS:g} s")


def use_voice(m: Loaded, ref: str | None) -> None:
    """Condition `m` on the reference recording `ref`, or on the built-in voice for None; a no-op when it is
    conditioned on `ref` already."""
    if ref == m.reference:
        return
    if ref is None:
        m.tts.conds = m.builtin
    else:
        check_reference(ref)
        m.tts.prepare_conditionals(ref)
    m.reference = ref


def speak(spec: ChatterboxProvider, entry: ChatterboxModel, name: str, model: str, text: str, voice: str) -> bytes:
    """A 24 kHz WAV file of `text` in `voice`."""
    from .speech import float_wav

    ref = reference(voice)
    with _lock, cpu.performance_threads():
        m = _load(spec, entry, model)
        use_voice(m, ref)
        audio = m.tts.generate(text).detach().cpu().numpy()
    return float_wav(audio, int(getattr(m.tts, "sr", SAMPLE_RATE)))
