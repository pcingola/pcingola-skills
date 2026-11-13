"""Request options of the CLI, the config task of each tier and image sizing per provider kind."""

from __future__ import annotations

import math

ASPECT_RATIOS = ("21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16")
IMAGE_SIZES = ("1K", "2K", "4K")
QUALITIES = ("low", "medium", "high", "auto")
BACKGROUNDS = ("auto", "opaque", "transparent")
# The config task of each --tier, without and with reference images.
TIER_TASKS = {"fast": ("image", "image_edit"), "best": ("image_best", "image_best"),
              "multi-ref": ("image_multi_ref", "image_multi_ref")}
TIERS = tuple(TIER_TASKS)
DEFAULT_TIER = "fast"
DEFAULT_ASPECT = "1:1"
DEFAULT_SIZE = "1K"


def task_for(tier: str, edit: bool) -> str:
    """The config task of `tier` for a generation (`edit` False) or an edit with reference images."""
    return TIER_TASKS[tier][edit]


def _ratio(aspect: str) -> float:
    w, h = aspect.split(":")
    return int(w) / int(h)


def fit_size(aspect: str, pixels: int, *, max_edge: int, step: int = 16,
             min_edge: int = 0) -> tuple[int, int]:
    """(width, height) of about `pixels` pixels in `aspect`, edges multiples of `step`, the long edge at most
    `max_edge`, the short edge at least `min_edge`."""
    r = _ratio(aspect)
    w = math.sqrt(pixels * r)
    h = math.sqrt(pixels / r)
    scale = min(1.0, max_edge / max(w, h))
    w = max(int(w * scale) // step * step, min_edge)
    h = max(int(h * scale) // step * step, min_edge)
    return w, h


# gpt-image-2 size limits: edges multiple of 16, longest edge <= 3840,
# total pixels in [655_360, 8_294_400].
_OPENAI_MAX_EDGE = 3840
_OPENAI_MIN_PIXELS = 655_360
_OPENAI_MAX_PIXELS = 8_294_400
_TARGET_PIXELS = {"1K": 1024 * 1024, "2K": 2048 * 2048, "4K": _OPENAI_MAX_PIXELS}
# Local diffusers models: edges multiples of 16 from 256 to 2048.
_LOCAL_MAX_EDGE = 2048
_LOCAL_MIN_EDGE = 256


def openai_size(aspect: str, size: str) -> tuple[int, int]:
    """(width, height) within the gpt-image-2 limits."""
    pixels = min(max(_TARGET_PIXELS[size], _OPENAI_MIN_PIXELS), _OPENAI_MAX_PIXELS)
    return fit_size(aspect, pixels, max_edge=_OPENAI_MAX_EDGE)


def local_size(aspect: str, size: str) -> tuple[int, int]:
    """(width, height) for a local diffusers model: 2K and 4K both fit the 2048 px long edge."""
    return fit_size(aspect, _TARGET_PIXELS[size], max_edge=_LOCAL_MAX_EDGE, min_edge=_LOCAL_MIN_EDGE)
