"""The look of a screencast: `screencast:` of settings.yaml with the shot list's `style:` merged over it.

Colours are written as `#RRGGBB` or as a name of `palette`. Screen sizes (blur radii, label sizes, margins)
are pixels of the output frame. The section's records live together in this module; `Style` holds them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import Color


class StyleError(ValueError):
    pass


class CaptionAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"


def hex_bgr(value: str) -> Color:
    """`#RRGGBB` as a BGR tuple of floats."""
    s = str(value).strip().lstrip("#")
    if len(s) != 6:
        raise StyleError(f"colour {value!r} is not #RRGGBB")
    try:
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise StyleError(f"colour {value!r} is not #RRGGBB") from None
    return float(b), float(g), float(r)


def parse_color(value: object, palette: dict[str, Color]) -> Color:
    """A palette name or `#RRGGBB` as a BGR tuple."""
    if isinstance(value, str) and value in palette:
        return palette[value]
    if isinstance(value, str) and value.startswith("#"):
        return hex_bgr(value)
    raise StyleError(f"colour {value!r} is neither #RRGGBB nor a palette name ({', '.join(palette)})")


@dataclass
class Glow:
    """A soft coloured light on the background drifting around (x, y), fractions of the frame."""
    x: float
    y: float
    radius: float
    color: Color
    amount: float


@dataclass
class Background:
    colors: tuple[Color, Color]
    glows: list[Glow]
    particles: int
    particle_color: Color


@dataclass
class PanelLook:
    radius: float
    shadow: float
    ambient_color: Color
    ambient: float
    edge_light: float


@dataclass
class LabelLook:
    font: str | None
    size: float
    fill: Color
    fill_opacity: float
    outline_opacity: float
    text: Color


@dataclass
class CaptionLook:
    band: bool
    band_color: Color
    band_opacity: float
    height: float
    ramp: float
    size: float
    align: CaptionAlign


@dataclass
class Style:
    palette: dict[str, Color]
    background: Background
    panel: PanelLook
    label: LabelLook
    caption: CaptionLook
    focal: float
    vignette: float
    safe_margin: float
    fade: float
    crf: int

    def color(self, value: object, default: str | None = None) -> Color:
        """A palette name or `#RRGGBB`; None gives the palette colour `default`."""
        return parse_color(value if value is not None else default, self.palette)

    @classmethod
    def parse(cls, d: dict) -> Style:
        try:
            palette = {str(k): hex_bgr(v) for k, v in (d.get("palette") or {}).items()}

            def c(v: object) -> Color:
                return parse_color(v, palette)
            bg, pn, lb, cp = d["background"], d["panel"], d["label"], d["caption"]
            try:
                align = CaptionAlign(cp["align"])
            except ValueError:
                raise StyleError("caption.align is left or center") from None
            return cls(
                palette=palette,
                background=Background(
                    colors=tuple(c(x) for x in bg["colors"]),
                    glows=[Glow(float(g["x"]), float(g["y"]), float(g["radius"]), c(g["color"]),
                                float(g["amount"])) for g in bg.get("glows") or []],
                    particles=int(bg["particles"]),
                    particle_color=c(bg["particle_color"])),
                panel=PanelLook(float(pn["radius"]), float(pn["shadow"]), c(pn["ambient_color"]),
                                float(pn["ambient"]), float(pn["edge_light"])),
                label=LabelLook(lb["font"], float(lb["size"]), c(lb["fill"]), float(lb["fill_opacity"]),
                                float(lb["outline_opacity"]), c(lb["text"])),
                caption=CaptionLook(bool(cp["band"]), c(cp["band_color"]), float(cp["band_opacity"]),
                                    float(cp["height"]), float(cp["ramp"]), float(cp["size"]), align),
                focal=float(d["focal"]), vignette=float(d["vignette"]), safe_margin=float(d["safe_margin"]),
                fade=float(d["fade"]), crf=int(d["crf"]),
            )
        except KeyError as e:
            raise StyleError(f"screencast style: missing {e.args[0]!r}") from None
        except (TypeError, ValueError) as e:
            if isinstance(e, StyleError):
                raise
            raise StyleError(f"screencast style: {e}") from None
