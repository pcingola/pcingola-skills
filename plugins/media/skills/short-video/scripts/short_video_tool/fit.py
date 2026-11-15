"""How a model clip is fitted into the `video:` frame (`video_scene.fill_filter`)."""

from __future__ import annotations

from enum import StrEnum


class Fit(StrEnum):
    """`COVER` scales the clip to cover the frame and crops the centre (video scenes). `CONTAIN` scales the clip to
    fit inside the frame, uncropped, over a blurred copy of itself scaled to cover the frame (presenter scenes,
    whose bucket may have another aspect than the film)."""

    COVER = "cover"
    CONTAIN = "contain"
