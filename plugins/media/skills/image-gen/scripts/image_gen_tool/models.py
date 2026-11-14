"""Request options of the CLI, the config task of each tier and image sizing per provider kind."""

from __future__ import annotations

import math
from dataclasses import dataclass

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


# Pixel count of each --size: 1K and 2K squares, 4K as 3840 x 2160.
_TARGET_PIXELS = {"1K": 1024 * 1024, "2K": 2048 * 2048, "4K": 3840 * 2160}


@dataclass(frozen=True)
class SizeLimits:
    """Image size limits and the request defaults of sized models, all from the settings (no model in code).

    `openai_*` bound the `dimensions` of an OpenAI-kind request; `local_*` the edges of a local diffusers
    image. `sized_models` are the OpenAI-kind model ids that always get `dimensions` (default aspect and
    size) and quality `sized_quality` unless the options say otherwise."""

    openai_max_edge: int
    openai_min_pixels: int
    openai_max_pixels: int
    local_max_edge: int
    local_min_edge: int
    sized_models: tuple[str, ...] = ()
    sized_quality: str | None = None

    @classmethod
    def from_settings(cls) -> SizeLimits:
        from . import config

        def num(key: str) -> int:
            v = config.PLUGIN.require(key)
            try:
                return int(v)
            except ValueError:
                config.PLUGIN.invalid(key, v, "an integer")

        models = config.PLUGIN.get("IMAGE_GEN_SIZED_MODELS") or ""
        return cls(
            openai_max_edge=num("IMAGE_GEN_OPENAI_MAX_EDGE"),
            openai_min_pixels=num("IMAGE_GEN_OPENAI_MIN_PIXELS"),
            openai_max_pixels=num("IMAGE_GEN_OPENAI_MAX_PIXELS"),
            local_max_edge=num("IMAGE_GEN_LOCAL_MAX_EDGE"),
            local_min_edge=num("IMAGE_GEN_LOCAL_MIN_EDGE"),
            sized_models=tuple(m.strip() for m in models.split(",") if m.strip()),
            sized_quality=config.PLUGIN.get("IMAGE_GEN_SIZED_QUALITY") or None,
        )


def openai_size(aspect: str, size: str, limits: SizeLimits) -> tuple[int, int]:
    """(width, height) within the `openai_*` limits."""
    pixels = min(max(_TARGET_PIXELS[size], limits.openai_min_pixels), limits.openai_max_pixels)
    return fit_size(aspect, pixels, max_edge=limits.openai_max_edge)


def local_size(aspect: str, size: str, limits: SizeLimits) -> tuple[int, int]:
    """(width, height) for a local diffusers model within the `local_*` limits."""
    return fit_size(aspect, _TARGET_PIXELS[size], max_edge=limits.local_max_edge, min_edge=limits.local_min_edge)
