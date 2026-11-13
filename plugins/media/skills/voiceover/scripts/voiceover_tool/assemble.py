"""Silence trimming, joining sentence clips with fixed gaps, and WAV output."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

DEFAULT_LEAD = 0.25
DEFAULT_GAP = 0.35
DEFAULT_TAIL = 0.6
SILENCE_DBFS = -50.0
KEEP_SECONDS = 0.030


def trim_silence(
    samples: np.ndarray, sr: int, threshold_dbfs: float = SILENCE_DBFS, keep: float = KEEP_SECONDS
) -> np.ndarray:
    """Remove leading and trailing audio below `threshold_dbfs`, keeping `keep` seconds.

    An all-silent clip returns an empty array.
    """
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    threshold = 10.0 ** (threshold_dbfs / 20.0)
    loud = np.flatnonzero(np.abs(samples) >= threshold)
    if loud.size == 0:
        return samples[:0]
    pad = int(round(keep * sr))
    first = max(0, int(loud[0]) - pad)
    last = min(samples.size, int(loud[-1]) + 1 + pad)
    return samples[first:last]


def join(
    clips: list[np.ndarray],
    sr: int,
    lead: float = DEFAULT_LEAD,
    gap: float = DEFAULT_GAP,
    tail: float = DEFAULT_TAIL,
) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Concatenate clips with `lead` silence before, `gap` between and `tail` after.

    Returns the audio and each clip's (start, end) in seconds from the start.
    """
    lead_n, gap_n, tail_n = (int(round(x * sr)) for x in (lead, gap, tail))
    parts: list[np.ndarray] = [np.zeros(lead_n, dtype=np.float32)]
    spans: list[tuple[float, float]] = []
    pos = lead_n
    for i, clip in enumerate(clips):
        clip = np.asarray(clip, dtype=np.float32).reshape(-1)
        if i > 0:
            parts.append(np.zeros(gap_n, dtype=np.float32))
            pos += gap_n
        spans.append((pos / sr, (pos + clip.size) / sr))
        parts.append(clip)
        pos += clip.size
    parts.append(np.zeros(tail_n, dtype=np.float32))
    return np.concatenate(parts), spans


def write_wav(path: str | Path, samples: np.ndarray, sr: int) -> Path:
    """Write mono 16-bit PCM WAV with the stdlib `wave` module."""
    path = Path(path)
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).round().astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path
