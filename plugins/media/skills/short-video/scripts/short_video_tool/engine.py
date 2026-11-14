"""The engines that make a scene's video, named by a scene's `Engine:`."""

from __future__ import annotations

from enum import StrEnum


class Engine(StrEnum):
    """A scene's engine. `HTML` (HyperFrames) is the default when a scene names none."""

    HTML = "html"
    MANIM = "manim"
    CLIP = "clip"
    VIDEO = "video"

    @classmethod
    def of(cls, scene: dict) -> Engine:
        """The engine of a parsed scene: its `engine`, else `HTML`."""
        return cls(scene.get("engine") or cls.HTML)
