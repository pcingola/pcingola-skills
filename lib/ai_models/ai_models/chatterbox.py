"""Chatterbox Turbo (provider kind `chatterbox`): local speech with zero-shot voice cloning, on the CPU, in the
caller's process (extra `ai-models[chatterbox]`).

A model entry (`providers.<p>.models.<m>`, `ChatterboxModel`) names its files, `files` under the repository URL
`url`, downloaded to `weights.model_dir`. The model is loaded once per weights directory and stays loaded for the life
of the process (`local.unload` and `local.unload_model` drop it); it needs no GPU and no local-model lock. A load of a
model whose entry sets `memory` is refused when the system's available memory is below it (`local.check_free`). One synthesis runs at a time
(`_lock`), because the loaded model holds the conditioning of one voice, on the fast cores of the CPU
(`cpu.performance_threads`).

A voice is `default` (the model's built-in voice) or the path of a reference recording longer than
`MIN_REFERENCE_SECONDS`; the model uses its first 10 to 15 s and copies the speaker and also the delivery,
microphone and room. The output is a 24 kHz WAV file with Resemble's Perth watermark (inaudible). There is no speed
or style control.

Cancellation: with a cancel signal (`cancel.signal`) the synthesis stops with `Cancelled` before the next forward of
the T3 transformer (`t3.tfmr`, once per speech token).

A model server's chatterbox model takes the recording in the speech request (`reference_field`): the request field
`REFERENCE_FIELD`, `{"data": <base64>, "format": <REFERENCE_FORMATS>}`, the shape of OpenAI's `input_audio`.
"""

from __future__ import annotations

import base64
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugin_settings import ChatterboxModel, ChatterboxProvider, ProviderKind

from . import cancel, config, cpu, local, weights
from .errors import AIModelsError

KIND = ProviderKind.CHATTERBOX
DEFAULT_VOICE = "default"
DEVICE = "cpu"
MIN_REFERENCE_SECONDS = 5.0
SAMPLE_RATE = 24_000
# The speech request field of a model server that carries a reference recording, and its formats: those of OpenAI's
# `input_audio` (wav, mp3) and FLAC, the formats the reader of the recording (soundfile) takes.
REFERENCE_FIELD = "reference_audio"
REFERENCE_FORMATS = ("wav", "mp3", "flac")


@dataclass
class Loaded:
    """A loaded model: `tts` (`ChatterboxTurboTTS`), the conditioning of its built-in voice, and the reference
    recording whose conditioning `tts` holds now (None: the built-in voice)."""

    tts: Any
    builtin: Any
    reference: str | None = None


_models: dict[Path, Loaded] = {}
_lock = threading.Lock()  # one load or synthesis at a time when callers run in several threads
local.on_unload(_models)


@local.on_unload_model
def _drop(model_id: str, weights_dir: Path | None) -> int:
    """Drop the loaded chatterbox model `model_id`, whose files are in its provider's `dir`, else in
    `weights_dir`."""
    if not _models or local.provider_kind(model_id) != KIND:
        return 0
    name, bare = config.split_id(model_id)
    d = weights.model_dir(config.provider(name).with_dir(weights_dir), bare)
    with _lock:
        return 0 if _models.pop(d, None) is None else 1


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
        if entry.memory is not None:
            local.check_free(entry.memory, str(d), f"the entry of {model}", DEVICE, False)
        import numpy as np
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        from transformers.initialization import no_init_weights

        # No random initialization: the strict `load_state_dict` of the checkpoint overwrites every weight.
        with no_init_weights():
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


def reference_field(voice: str) -> dict[str, str]:
    """The `REFERENCE_FIELD` value of the recording `voice` (a path): its bytes in base64 and its format, from its
    suffix; `AIModelsError` for a missing file or a suffix outside `REFERENCE_FORMATS`."""
    p = Path(reference(voice) or voice)
    fmt = p.suffix.lower().lstrip(".")
    if fmt not in REFERENCE_FORMATS:
        raise AIModelsError(f"{p}: a reference sent to a model server is one of "
                            f"{', '.join('.' + f for f in REFERENCE_FORMATS)}")
    return {"data": base64.b64encode(p.read_bytes()).decode("ascii"), "format": fmt}


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
        cancel.check()
        with cancel.hooked(m.tts.t3.tfmr):
            audio = m.tts.generate(text).detach().cpu().numpy()
    return float_wav(audio, int(getattr(m.tts, "sr", SAMPLE_RATE)))
