"""The frame rate of the test projects that render with HyperFrames or Manim.

A HyperFrames render costs about 4 s of browser start and page load plus about 35 ms per 1080p frame, so a 2 s
scene at the default 30 fps takes about 6.5 s and at 10 fps about 4.5 s. Frame size stays at the default 1920x1080:
it changes the render time little, and the tests' pixel positions are in 1080p coordinates.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from short_video_tool import settings

FPS = 10


def set_fps(project: Path) -> None:
    """Set `video.fps` to FPS in the project's settings.yaml, keeping its other settings; creates the file when
    missing."""
    path = project / settings.PROJECT_FILE
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None) or {}
    path.write_text(yaml.safe_dump(settings.merge(data, {"video": {"fps": FPS}})), encoding="utf-8")
