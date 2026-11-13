"""Small FFmpeg / ffprobe / subprocess helpers shared by scenes, mix and music."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class ToolError(Exception):
    """An external command failed."""


def num(x: float) -> str:
    """A number for an FFmpeg filter or an HTML attribute: at most three
    decimals, no trailing zeros (6.2, not 6.200)."""
    return f"{x:.3f}".rstrip("0").rstrip(".")


def which(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolError(f"{name} not found on PATH")
    return path


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, capture: bool = True,
        text: bool = True) -> subprocess.CompletedProcess:
    """Run a command; raise ToolError with its output tail on a non-zero exit.
    `text=False` returns stdout and stderr as bytes."""
    proc = subprocess.run(
        [str(c) for c in cmd], cwd=cwd, env=env, text=text,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "") if text else \
            (proc.stdout or b"").decode(errors="replace") + (proc.stderr or b"").decode(errors="replace")
        tail = "\n".join(out.strip().splitlines()[-30:])
        raise ToolError(f"command failed ({proc.returncode}): {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    return proc


def probe(path: Path) -> dict:
    out = run([which("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout
    return json.loads(out)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def video_duration(path: Path) -> float:
    """Duration of the first video stream (falls back to the container)."""
    info = probe(path)
    for s in info["streams"]:
        if s.get("codec_type") == "video" and s.get("duration"):
            return float(s["duration"])
    return float(info["format"]["duration"])



def video_size(path: Path) -> tuple[int, int]:
    """(width, height) of the first video stream."""
    s = next(s for s in probe(path)["streams"] if s.get("codec_type") == "video")
    return int(s["width"]), int(s["height"])
