"""The `speech` backend: the `speech` model of the `ai_models` config through
`ai_models.speech.speak`, one request per sentence.

A style goes as the model's `instructions` (OpenAI-style providers) or as a
prefix of the text (Gemini TTS). A speed (0.25 to 4) goes to OpenAI-style
providers, which may refuse it (Ollama does); Gemini TTS has none. The answer is
a WAV file, resampled to 24 kHz when it has another rate (Drama 3: 44.1 kHz); raw 16-bit PCM (some
OpenAI-compatible servers) is taken as 24 kHz. The voice is checked by the provider. The default voice is the setting
VOICEOVER_SPEECH_VOICE; `voices` lists VOICEOVER_SPEECH_VOICES when set.

A model of kind vllm-omni (Fish Audio Drama 3) has no voices and no speed. Its voice is `default` (the model's
own voice) or a reference voice of `add-voice` (a name in the voices directory, or a path) whose transcript
`<name>.txt` lies beside it; the model clones it. A style becomes the provider's `style` format, inline tags for
Drama 3 (`--style whisper` sends `[whisper] <sentence>`).
"""

from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 24_000
TASK = "speech"

SPEED_RANGE = (0.25, 4.0)


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


class SpeechBackend:
    """The config's `speech` model. `ValueError` when the config names none."""

    name = "speech"
    sample_rate = SAMPLE_RATE

    def __init__(self, style: str | None = None) -> None:
        from ai_models import AIModelsError
        from ai_models import config as ai_config
        from ai_models.models import kind

        try:
            self.model = ai_config.resolve(None, TASK)
            self.kind = kind(self.model)
        except AIModelsError as e:
            raise ValueError(str(e)) from None
        self.style = style
        from . import config

        self.default_voice = config.require("VOICEOVER_SPEECH_VOICE")
        listed = [v.strip() for v in (config.PLUGIN.get("VOICEOVER_SPEECH_VOICES") or "").split(",") if v.strip()]
        self._voices = listed or [self.default_voice]

    def voices(self) -> list[str]:
        return list(self._voices)

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        from ai_models import omni

        if self.kind == omni.KIND and voice != omni.DEFAULT_VOICE:
            from .chatterbox import reference_path

            voice = str(reference_path(voice))
        if speed != 1.0 and self.kind in ("google", omni.KIND):
            raise ValueError(f"{self.model} has no speed setting; ask for the pace with --style instead")
        lo, hi = SPEED_RANGE
        if not lo <= speed <= hi:
            raise ValueError(f"speech speed must be between {lo} and {hi}")
        from ai_models import AIModelsError, speech

        try:
            data = speech.speak(text, voice=voice, model=self.model, instructions=self.style, speed=speed)
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
