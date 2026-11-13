"""Spectrogram and waveform images of a clip with FFmpeg.

The spectrogram is `showspectrumpic` with a logarithmic frequency axis and
legend (time and frequency scales); the waveform is `showwavespic` with one
lane per channel, on white.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SPECTROGRAM_SIZE = "1200x600"
WAVEFORM_SIZE = "1200x300"


class ImageError(Exception):
    """FFmpeg failed to draw an image."""


def spectrogram_filter(size: str = SPECTROGRAM_SIZE) -> str:
    return f"showspectrumpic=s={size}:fscale=log:scale=log:legend=1"


def waveform_filter(size: str = WAVEFORM_SIZE) -> str:
    """showwavespic draws on a transparent background; it is laid over white."""
    return (f"[0:a]showwavespic=s={size}:split_channels=1:colors=0x1f4e9c|0x9c1f1f[w];"
            f"color=c=white:s={size}[bg];[bg][w]overlay=format=auto")


def _draw(src: Path, out: Path, graph: str) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ImageError("ffmpeg not found on PATH")
    proc = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-lavfi", graph, "-frames:v", "1", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise ImageError(f"ffmpeg failed on {src.name}: {proc.stderr.strip()[-500:]}")
    return out


def draw(src: Path, spectrogram: Path, waveform: Path) -> dict:
    _draw(src, spectrogram, spectrogram_filter())
    _draw(src, waveform, waveform_filter())
    return {"status": "ok", "spectrogram": spectrogram.name, "waveform": waveform.name}
