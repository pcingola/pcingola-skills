"""The shot list as data: what `shotlist.load` reads from the YAML file.

Page coordinates are in page pixels: source image pixels divided by the
shot's `scale` (2 for a 2x screenshot or a 3840x2160 recording of a 1920x1080
page). Screen coordinates are pixels of the output frame. Times inside a shot
are seconds from the shot's start. Colours are BGR tuples of 0..255 floats.

The record types of the format live together in this one module: each is a
plain record of a few fields, and together they are the format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

Color = tuple[float, float, float]
Rect = tuple[float, float, float, float]
Point = tuple[float, float]


class ShotKind(str, Enum):
    PANEL = "panel"
    PICTURE = "picture"
    CARDS = "cards"


class Shape(str, Enum):
    BOX = "box"
    ELLIPSE = "ellipse"


class Anchor(str, Enum):
    """Which point of a label `at` names: its top-left, top-centre or top-right corner."""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class LabelEdge(str, Enum):
    """Where a wipe's two labels sit along the divider."""
    TOP = "top"
    BOTTOM = "bottom"


@dataclass
class CameraSpec:
    """A camera key as written: a field left None keeps the previous key's value (the first key's default
    frames the whole page). `rect` sets centre and zoom so the rect fits the frame; `width` sets the zoom so
    that many page px span the frame width."""
    t: float
    center: Point | None = None
    zoom: float | None = None
    width: float | None = None
    rect: Rect | None = None
    yaw: float | None = None
    pitch: float | None = None


@dataclass
class CameraKey:
    """A camera key: at time `t`, page point `center` in the frame centre at `zoom` screen px per page px,
    the panel turned `yaw` degrees about the vertical axis and `pitch` about the horizontal one."""
    t: float
    center: Point
    zoom: float
    yaw: float = 0.0
    pitch: float = 0.0


@dataclass
class Highlight:
    """A glowing outline around a page rect, faded in and out over `fade` s; `grow` draws it from its top-left
    corner (a box) or its left end (an ellipse)."""
    start: float
    end: float
    rect: Rect
    color: Color
    shape: Shape = Shape.BOX
    grow: bool = False
    pulse: bool = True
    fade: float = 0.3


@dataclass
class Click:
    """A ripple expanding from page point `at` over 0.7 s from time `t`."""
    t: float
    at: Point
    color: Color


@dataclass
class Label:
    """A rounded label with a coloured dot. `at` is a screen point, or a page point when `page` is true;
    a caption sits in the caption band instead and ignores `at`."""
    text: str
    start: float
    end: float
    color: Color
    at: Point | None = None
    page: bool = False
    anchor: Anchor = Anchor.LEFT
    size: float | None = None
    caption: bool = False


@dataclass
class Draw:
    """A box or ellipse drawn onto the page between `start` and `end`, as a user draws it in the UI."""
    shape: Shape
    rect: Rect
    start: float
    end: float
    color: Color
    width: float = 2.0


@dataclass
class Patch:
    """A page rect painted over before anything else: copied from page point `source` (its top-left), or
    filled with `color`, or, with neither, with the median colour of the pixels around it."""
    rect: Rect
    source: Point | None = None
    color: Color | None = None


@dataclass
class Typing:
    """Text in page rect `rect` of the source image typed glyph by glyph between `start` and `end`; the
    glyphs are the ink runs of the finished text, line by line."""
    rect: Rect
    start: float
    end: float
    caret: bool = True
    caret_color: Color | None = None
    threshold: float = 40.0


@dataclass
class Insert:
    """A video (its `from`..`to` re-timed to the shot) or a picture warped into page rect `rect`, drawn over
    the page at its own resolution (a film playing in the page)."""
    rect: Rect
    video: Path | None = None
    image: Path | None = None
    start: float = 0.0
    end: float | None = None


@dataclass
class Wipe:
    """Before left of the divider, after right of it. `divider` keys the divider's page x over time; `after`
    is aligned to `before` (ECC, affine) when `align` is true."""
    before: Path
    after: Path
    divider: list[tuple[float, float]]
    color: Color
    labels: tuple[str, str] | None = None
    label_colors: tuple[Color, Color] | None = None
    label_edge: LabelEdge = LabelEdge.TOP
    fade: tuple[float, float] | None = None
    align: bool = True


@dataclass
class Grade:
    """A tone change of the page or picture: out = 255 * gain * (in / 255) ** gamma, then each channel times
    `tint` (R, G, B). gamma 1.6, gain 0.62, tint (0.92, 1.0, 1.12) sets a light-mode capture into a dark film."""
    gamma: float = 1.0
    gain: float = 1.0
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class CardPose:
    t: float
    center: Point
    width: float
    angle: float = 0.0
    alpha: float = 1.0


@dataclass
class Card:
    image: Path
    keys: list[CardPose]
    upscale: int | None = None


@dataclass
class Shot:
    kind: ShotKind
    length: float
    fade: float
    index: int = 0
    video: Path | None = None
    image: Path | None = None
    wipe: Wipe | None = None
    start: float = 0.0
    end: float | None = None
    times: list[tuple[float, float]] | None = None
    scale: float = 1.0
    upscale: int | None = None
    rect: Rect | None = None
    radius: float | None = None
    camera: list[CameraSpec] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)
    clicks: list[Click] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    draws: list[Draw] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    typing: list[Typing] = field(default_factory=list)
    inserts: list[Insert] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    glow: Color | None = None
    grade: Grade | None = None


@dataclass
class ShotList:
    path: Path
    shots: list[Shot]
    style: dict

    @property
    def length(self) -> float:
        return sum(s.length for s in self.shots)

    @property
    def has_captions(self) -> bool:
        return any(lb.caption for s in self.shots for lb in s.labels)
