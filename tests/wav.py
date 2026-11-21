"""`read`: the samples of a 16-bit WAV file that a speech model answered."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Wav:
    """The samples of a WAV file as floats in [-1, 1] ([frames, channels]), its `rate` and its channel count."""

    samples: np.ndarray
    rate: int
    channels: int

    @property
    def seconds(self) -> float:
        """The duration in seconds."""
        return self.samples.shape[0] / self.rate

    @property
    def rms(self) -> float:
        """The root mean square of the samples."""
        return float(np.sqrt(np.mean(self.samples**2)))


def read(data: bytes) -> Wav:
    """The `Wav` of the 16-bit WAV file `data`; AssertionError when its samples are not 16-bit."""
    with wave.open(io.BytesIO(data)) as w:
        assert w.getsampwidth() == 2, f"{8 * w.getsampwidth()}-bit samples, expected 16-bit"
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        return Wav(frames.reshape(-1, w.getnchannels()), w.getframerate(), w.getnchannels())


def reference(take: bytes, seconds: float = 5.5) -> bytes:
    """A 16-bit mono WAV file of the speech `take` repeated, with half a second of silence after each, until it lasts
    at least `seconds`: a reference recording longer than Chatterbox's 5 s minimum."""
    w = read(take)
    one = np.concatenate([w.samples[:, 0], np.zeros(w.rate // 2, np.float32)])
    samples = np.tile(one, int(np.ceil(seconds * w.rate / one.size)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(w.rate)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()
