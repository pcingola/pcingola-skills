"""`brand:`: directories searched for brand folders after the bundled brands, in order."""

from __future__ import annotations

from .base import Strict
from .fields import UserPath


class BrandSettings(Strict):
    """`path`: a missing directory is skipped by the reader."""

    path: list[UserPath] = []
