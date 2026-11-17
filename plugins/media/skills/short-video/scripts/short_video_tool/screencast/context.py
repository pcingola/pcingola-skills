"""What every shot renderer of one render shares: the frame size, the style, the stage and the label painter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .labels import LabelPainter
from .stage import Stage
from .style import Style


@dataclass
class RenderContext:
    frame: tuple[int, int]
    style: Style
    stage: Stage
    labels: LabelPainter
    band: bool
    warn: Callable[[str], None]

    @classmethod
    def make(cls, style: Style, frame: tuple[int, int], band: bool, warn: Callable[[str], None]) -> RenderContext:
        stage = Stage(style, frame)
        return cls(frame, style, stage, LabelPainter(style, frame, stage.project), band, warn)
