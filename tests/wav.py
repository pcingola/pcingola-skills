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
