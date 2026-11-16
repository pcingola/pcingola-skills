"""A provider whose requests have a time limit."""

from __future__ import annotations

from pydantic import PositiveFloat

from ..base import Strict

DEFAULT_TIMEOUT = 600.0


class TimedProvider(Strict):
    """`timeout`: seconds per request."""

    timeout: PositiveFloat = DEFAULT_TIMEOUT
