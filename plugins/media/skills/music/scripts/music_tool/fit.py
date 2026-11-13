"""Loop or trim a track to an exact length with FFmpeg, with fades.

The input is read with `-stream_loop -1`, so a track shorter than the target
repeats; `-t` cuts it at the target. The codec follows the output extension.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CODECS = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    ".wav": ["-c:a", "pcm_s16le"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
}


class FitError(Exception):
    """Invalid fit request or FFmpeg failure."""


def _num(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def build_command(src: Path, out: Path, seconds: float, fade_in: float = 0.0, fade_out: float = 2.0,
                  ffmpeg: str = "ffmpeg") -> list[str]:
    ext = out.suffix.lower()
    if ext not in CODECS:
        raise FitError(f"output must end in {', '.join(CODECS)}, got {out.name}")
    if seconds <= 0:
        raise FitError("--seconds must be positive")
    if fade_in < 0 or fade_out < 0:
        raise FitError("fades must not be negative")
    if fade_in + fade_out > seconds:
        raise FitError(f"fade-in {_num(fade_in)} s plus fade-out {_num(fade_out)} s exceed {_num(seconds)} s")
    filters = []
    if fade_in:
        filters.append(f"afade=t=in:d={_num(fade_in)}")
    if fade_out:
        filters.append(f"afade=t=out:st={_num(seconds - fade_out)}:d={_num(fade_out)}")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src), "-vn"]
    if filters:
        cmd += ["-af", ",".join(filters)]
    return cmd + ["-t", _num(seconds), *CODECS[ext], str(out)]


def fit(src: Path, out: Path, seconds: float, fade_in: float = 0.0, fade_out: float = 2.0) -> Path:
    if not src.is_file():
        raise FitError(f"{src} not found")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FitError("ffmpeg not found on PATH")
    cmd = build_command(src, out, seconds, fade_in, fade_out, ffmpeg)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FitError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()[-1000:]}")
    return out


def encode(audio: bytes, out: Path) -> Path:
    """Write the audio file `audio` to `out`, encoded by FFmpeg by the extension of `out` (CODECS)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FitError("ffmpeg not found on PATH")
    proc = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
                           *CODECS[out.suffix.lower()], str(out)], input=audio, capture_output=True)
    if proc.returncode != 0:
        raise FitError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.decode(errors='replace').strip()[-1000:]}")
    return out


def duration(path: Path) -> float | None:
    """Duration in seconds from ffprobe; None when ffprobe is missing or fails."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return round(float(proc.stdout.strip()), 3)
    except ValueError:
        return None
