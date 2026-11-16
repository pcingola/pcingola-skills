"""The image quality an OpenAI-style image model takes."""

from __future__ import annotations

from enum import StrEnum


class Quality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTO = "auto"
