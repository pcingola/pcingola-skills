"""Fixed value sets of the project format: stage sizes and timing libraries."""
from __future__ import annotations

from enum import Enum


class Size(Enum):
    """Aspect ratio of the stage and its size in stage pixels."""

    WIDE = "16:9"
    TALL = "9:16"
    SQUARE = "1:1"
    PORTRAIT = "4:5"

    @property
    def pixels(self) -> tuple[int, int]:
        return {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}[self.value]


class TimingLib(Enum):
    """The library that builds the chapter timelines; the player has one adapter per value."""

    GSAP = "gsap"
    ANIME = "anime"
    MOTION = "motion"


class ExtraLib(Enum):
    """Libraries a chapter draws with; the timing library drives them."""

    D3 = "d3"
    THREE = "three"


class Rule(Enum):
    """The rules `validate` checks; each error names one."""

    FORMAT = "format"            # animation.json, content.json, chapter files, lib/, player.js
    BUILD = "build"              # index.html equals what build writes now
    CHAPTER = "chapter"          # one HA.chapter("<id>", ...) call per script, with its own id
    DETERMINISM = "determinism"  # no timers, clocks, Math.random, self-running playback
    CSS_MOTION = "css-motion"    # no CSS animations or transitions
    OFFLINE = "offline"          # no remote URLs, no fetch
    ID = "id"                    # every element in a chapter html has a unique id
    TARGET = "target"            # scripts reach elements by id only, and those ids exist
    CONTENT = "content"          # every content.json key is used, and every content key used exists
    LIB = "lib"                  # globals used are of libraries present in lib/
