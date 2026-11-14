"""Chatterbox Turbo: local TTS with zero-shot voice cloning; the weights are settings (`config.py`).

A voice is a reference recording: `<name>.wav` in `config.voices_dir()`, or a
path to an audio file. `default` is the model's built-in voice. The model uses
the first 10-15 s of the recording, which must be longer than 5 s; it copies
the speaker and also the delivery, microphone and room of the recording.

Output is 24 kHz mono and carries Resemble's Perth watermark (inaudible). Turbo
has no speed or style control. Runs on CPU, which was faster than MPS on an
Apple-silicon Mac.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from . import config, download

BUILTIN_VOICE = "default"  # the name of the model's built-in voice (no reference recording)
MIN_REFERENCE_SECONDS = 5.0
AUDIO_SUFFIXES = (".wav", ".flac", ".mp3", ".m4a")


def voice_names() -> list[str]:
    """`default` plus the name of every recording in the voices directory."""
    d = config.voices_dir()
    names = sorted(p.stem for p in d.iterdir() if p.suffix.lower() in AUDIO_SUFFIXES) if d.is_dir() else []
    return [BUILTIN_VOICE] + names


def reference_path(voice: str) -> Path | None:
    """The recording for `voice` (None for the built-in voice)."""
    if voice == BUILTIN_VOICE:
        return None
    p = Path(voice).expanduser()
    if p.suffix.lower() in AUDIO_SUFFIXES and p.is_file():
        return p
    d = config.voices_dir()
    for suffix in AUDIO_SUFFIXES:
        p = d / f"{voice}{suffix}"
        if p.is_file():
            return p
    raise ValueError(
        f"unknown chatterbox voice {voice!r}: no {voice}.wav in {d}; "
        "add one with `voiceover.sh add-voice NAME FILE`"
    )


class ChatterboxBackend:
    name = "chatterbox"
    sample_rate = 24_000

    @property
    def default_voice(self) -> str:
        return config.require("VOICEOVER_CHATTERBOX_VOICE")

    @property
    def model(self) -> str:
        return config.chatterbox_model()

    def __init__(self, style: str | None = None) -> None:
        if style:
            raise ValueError("chatterbox takes no style; the delivery follows the reference recording")
        self._tts = None
        self._voice: str | None = None

    def voices(self) -> list[str]:
        return voice_names()

    def _load(self):
        if self._tts is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            for w in download.chatterbox_weights():
                download.ensure_weight(w)
            tts = ChatterboxTurboTTS.from_local(config.model_dir() / config.chatterbox_model(), "cpu")
            # Under numpy 2 the loudness gain (a float64 scalar) promotes the
            # float32 reference to float64, which the mel filter matmul rejects.
            norm = tts.norm_loudness
            tts.norm_loudness = lambda wav, sr, target_lufs=-27: np.asarray(norm(wav, sr, target_lufs), dtype=np.float32)
            self._builtin = tts.conds
            self._tts = tts
        return self._tts

    def _use_voice(self, voice: str) -> None:
        ref = reference_path(voice)
        tts = self._load()
        if voice == self._voice:
            return
        if ref is None:
            tts.conds = self._builtin
        else:
            import soundfile as sf

            info = sf.info(str(ref))
            if info.duration <= MIN_REFERENCE_SECONDS:
                raise ValueError(f"{ref}: {info.duration:.1f} s; a reference must be longer than {MIN_REFERENCE_SECONDS:g} s")
            tts.prepare_conditionals(str(ref))
        self._voice = voice

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        if speed != 1.0:
            raise ValueError("chatterbox has no speed control; use --speed 1.0")
        self._use_voice(voice)
        wav = self._tts.generate(text)
        return wav.detach().cpu().numpy().astype(np.float32).reshape(-1)
