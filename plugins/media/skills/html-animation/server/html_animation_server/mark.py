"""A mark on a paused frame: a point or a rectangle in stage pixels."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .http_error import HttpError
from .kinds import MarkKind


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise HttpError(400, f"{what} must be a finite number")
    return float(value)


def _short(x: float) -> str:
    """`x` rounded to one decimal, without a trailing `.0`."""
    return f"{round(x, 1):g}"


@dataclass(frozen=True)
class Mark:
    """`kind` is `point` (x, y) or `rect` (x, y, w, h); w and h are 0 for a point."""

    kind: MarkKind
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0

    @classmethod
    def from_json(cls, value: object) -> Mark:
        """`{point: {x, y}}` or `{rect: {x, y, w, h}}`; 400 otherwise. A rectangle needs a positive w and h."""
        if not isinstance(value, dict) or len(value) != 1:
            raise HttpError(400, "mark must be {point: {x, y}} or {rect: {x, y, w, h}}")
        if isinstance(value.get("point"), dict):
            p = value["point"]
            return cls(MarkKind.POINT, _number(p.get("x"), "point.x"), _number(p.get("y"), "point.y"))
        if isinstance(value.get("rect"), dict):
            r = value["rect"]
            w, h = _number(r.get("w"), "rect.w"), _number(r.get("h"), "rect.h")
            if w <= 0 or h <= 0:
                raise HttpError(400, "rect.w and rect.h must be positive")
            return cls(MarkKind.RECT, _number(r.get("x"), "rect.x"), _number(r.get("y"), "rect.y"), w, h)
        raise HttpError(400, "mark must be {point: {x, y}} or {rect: {x, y, w, h}}")

    def to_json(self) -> dict:
        if self.kind is MarkKind.POINT:
            return {"point": {"x": self.x, "y": self.y}}
        return {"rect": {"x": self.x, "y": self.y, "w": self.w, "h": self.h}}

    def cli_arg(self) -> str:
        """The `--mark` argument of the CLI's `still`: `point:X,Y` or `rect:X,Y,W,H`."""
        values = (self.x, self.y) if self.kind is MarkKind.POINT else (self.x, self.y, self.w, self.h)
        return f"{self.kind.value}:" + ",".join(_short(v) for v in values)

    def describe(self) -> str:
        """The mark in words, for the prompt."""
        if self.kind is MarkKind.POINT:
            return f"a point at x={_short(self.x)}, y={_short(self.y)} stage pixels"
        return (f"a rectangle at x={_short(self.x)}, y={_short(self.y)}, width {_short(self.w)}, "
                f"height {_short(self.h)} stage pixels")
