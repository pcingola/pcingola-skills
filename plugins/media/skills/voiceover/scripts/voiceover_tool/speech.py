"""The narrator: a speech model of the `ai_models` config (`--model`, else `models.speech`), one request per
sentence through `ai_models.speech.speak`.

`ai_models.speech.check` refuses a speed or a style the model does not take when the narrator is made, before
any request or model load. The style goes as the model's instructions. The default voice is the model's
(`ai_models` provider `voice`, else its kind's). A model whose kind clones a voice (chatterbox, vllm-omni) also
takes a reference recording of `add-voice` (`voices.py`), passed as its path; `voices` lists those after the
model's own voices. The answer is a WAV file, resampled to 24 kHz when it has another rate (Drama 3: 44.1 kHz); raw
16-bit PCM (some OpenAI-compatible servers) is taken as 24 kHz.

A vllm-omni model (Fish Audio Drama 3) with the voice `default` keeps the first sentence's take as the reference
of the rest, so one command has one speaker; `synth` writes it as `voice.wav` + `voice.txt`.
"""

from __future__ import annotations

import io
import wave

import numpy as np

from . import voices
from .script import split_style

SAMPLE_RATE = 24_000


class TTSError(Exception):
    """A TTS request failed or returned unusable audio."""


def pcm16_to_float(data: bytes) -> np.ndarray:
    """Little-endian signed 16-bit PCM -> float32 in [-1, 1)."""
    if len(data) % 2:
        data = data[:-1]
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def decode(data: bytes) -> tuple[np.ndarray, int]:
    """Mono float32 samples and the sample rate of a 16-bit WAV file, or of raw 16-bit PCM at 24 kHz."""
    if data[:4] != b"RIFF":
        return pcm16_to_float(data), SAMPLE_RATE
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise TTSError(f"expected 16-bit audio, got {8 * w.getsampwidth()}-bit")
        samples = pcm16_to_float(w.readframes(w.getnframes()))
        return samples.reshape(-1, w.getnchannels()).mean(axis=1), w.getframerate()


def resample(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """`samples` at `rate` Hz resampled to `target` Hz (torchaudio's band-limited sinc interpolation)."""
    import torch
    import torchaudio.functional as F

    return F.resample(torch.from_numpy(np.ascontiguousarray(samples)), rate, target).numpy()


class Narrator:
    """Speech model `model` (else `models.speech`) with `style` and `speed`; `ValueError` when the config names no
    such model or the model does not take the style or speed."""

    sample_rate = SAMPLE_RATE

    def __init__(self, model: str | None = None, style: str | None = None, speed: float = 1.0) -> None:
        from ai_models import AIModelsError
        from ai_models import speech

        try:
            m = speech.check(model, speed=speed, instructions=style)
        except AIModelsError as e:
            raise ValueError(str(e)) from None
        self.model, self.kind, self.default_voice = m.id, m.kind, m.default_voice
        self.clones, self.instructions = m.traits.clones, m.instructions
        self.style, self.speed = style, speed

    def lines(self, sentences: list[str]) -> list[tuple[str | None, str]]:
        """(own style, sentence) of each script line. A line starting with `[style]` gives that style only when the
        model takes styles (`split_style`), which then takes any style; for other models the line is literal text."""
        return [split_style(s) for s in sentences] if self.instructions else [(None, s) for s in sentences]

    def voices(self) -> list[str]:
        """The model's voices, then the reference recordings when the model clones a voice."""
        from ai_models import speech

        own = speech.voices(self.model)
        return own + [v for v in voices.names() if v not in own] if self.clones else own

    def first_take(self) -> tuple[bytes, str] | None:
        """(WAV, text) of the first `default`-voice sentence of a vllm-omni model in this process, else None."""
        from ai_models import omni

        return omni.first_take(self.model.partition(":")[0]) if self.kind == omni.KIND else None

    def synthesize(self, text: str, voice: str, style: str | None = None) -> np.ndarray:
        """Mono float32 samples of `text` at `sample_rate`, with `style` (else the narrator's)."""
        from ai_models import AIModelsError, speech

        if self.clones and voice != voices.DEFAULT_VOICE:
            voice = str(voices.reference_path(voice))
        try:
            data = speech.speak(text, voice=voice, model=self.model, instructions=style or self.style,
                                speed=self.speed)
        except AIModelsError as e:
            msg = str(e)
            raise TTSError(msg if msg.startswith(self.model) else f"{self.model}: {msg}") from None
        except Exception as e:
            if getattr(e, "status_code", None) is None:
                raise
            raise TTSError(f"{self.model}: {e}") from None  # the provider refused the request (a voice it lacks)
        samples, rate = decode(data)
        if rate != self.sample_rate:
            samples = resample(samples, rate, self.sample_rate)
        if not samples.size:
            raise TTSError(f"{self.model} returned no audio for: {text[:80]!r}")
        return samples
