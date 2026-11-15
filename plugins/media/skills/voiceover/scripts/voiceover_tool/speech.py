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
from .script import Line

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
    """Speech model `model` (else `models.speech`) with `style`, `speed`, the voice of each named speaker
    (`speakers`, a name of `@name` lines to a voice) and more request fields (`params`); `ValueError` when the config
    names no such model or the model does not take the style, speed, speakers or parameters."""

    sample_rate = SAMPLE_RATE

    def __init__(self, model: str | None = None, style: str | None = None, speed: float = 1.0,
                 speakers: dict[str, str] | None = None, params: dict | None = None) -> None:
        from ai_models import AIModelsError
        from ai_models import speech

        try:
            m = speech.check(model, speed=speed, instructions=style, params=params)
        except AIModelsError as e:
            raise ValueError(str(e)) from None
        self.model, self.kind, self.default_voice = m.id, m.kind, m.default_voice
        self.clones, self.instructions, self.tags = m.traits.clones, m.instructions, m.traits.tags
        if speakers and not self.tags:
            raise ValueError(f"{m.id} takes no speakers (`@speaker` lines are for a model that takes inline tags)")
        self.style, self.speed, self.speakers, self.params = style, speed, dict(speakers or {}), dict(params or {})
        self.made_up: list[str] = []  # the speakers of `@name` lines without a voice, in order of first line

    def lines(self, sentences: list[str]) -> list[Line]:
        """Each script line as the model takes it (`Line.of`): speakers and inline tags for a model that takes tags,
        a leading `[style]` for one that takes styles, else literal text."""
        return [Line.of(s, styles=self.instructions, tags=self.tags) for s in sentences]

    def voices(self) -> list[str]:
        """The model's voices, then the reference recordings when the model clones a voice."""
        from ai_models import speech

        own = speech.voices(self.model)
        return own + [v for v in voices.names() if v not in own] if self.clones else own

    def first_takes(self) -> dict[str | None, tuple[bytes, str]]:
        """Per speaker (None: the narrator), (WAV, text) of its first `default`-voice sentence of a vllm-omni model in
        this process; empty for other kinds."""
        from ai_models import omni

        if self.kind != omni.KIND:
            return {}
        name = self.model.partition(":")[0]
        return {s: t for s in (None, *self.made_up) if (t := omni.first_take(name, s))}

    def voice_of(self, line: Line, voice: str) -> str:
        """The voice of `line`: its speaker's (`speakers`, else `default`, a made-up speaker), else `voice`."""
        if line.speaker is None:
            return voice
        if line.speaker not in self.speakers and line.speaker not in self.made_up:
            self.made_up.append(line.speaker)
        return self.speakers.get(line.speaker, voices.DEFAULT_VOICE)

    def synthesize(self, line: Line, voice: str) -> np.ndarray:
        """Mono float32 samples of `line` at `sample_rate`, in its speaker's voice (else `voice`), with its own
        style (else the narrator's)."""
        from ai_models import AIModelsError, speech

        voice = self.voice_of(line, voice)
        if self.clones and voice != voices.DEFAULT_VOICE:
            voice = str(voices.reference_path(voice))
        try:
            data = speech.speak(line.said, voice=voice, model=self.model, instructions=line.style or self.style,
                                speed=self.speed, speaker=line.speaker, params=self.params or None)
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
            raise TTSError(f"{self.model} returned no audio for: {line.said[:80]!r}")
        return samples
