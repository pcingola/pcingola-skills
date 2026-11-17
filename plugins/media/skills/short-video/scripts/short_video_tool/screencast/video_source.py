"""A video file's stream format, and forward readers of its frames (`FrameStream`)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from .. import media
from .frame_stream import FrameStream


class VideoSource:
    def __init__(self, path: Path):
        self.path = path
        info = media.probe(path)
        s = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if s is None:
            raise ValueError(f"{path} has no video stream")
        self.width, self.height = int(s["width"]), int(s["height"])
        self.fps = float(Fraction(s.get("r_frame_rate") or s.get("avg_frame_rate") or "30/1"))
        self.duration = float(s.get("duration") or info["format"]["duration"])

    def stream(self) -> FrameStream:
        return FrameStream(self.path, self.width, self.height, self.fps, self.duration)
