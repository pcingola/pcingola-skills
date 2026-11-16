"""A local provider whose models run in a process of another Python environment."""

from __future__ import annotations

from pydantic import PositiveFloat

from ..fields import UserPath
from .timed import DEFAULT_TIMEOUT, TimedProvider


class OwnEnvironment(TimedProvider):
    """`python`: the interpreter of that environment; `start_timeout`: seconds the start may take; `timeout`:
    seconds per request."""

    python: UserPath
    start_timeout: PositiveFloat = DEFAULT_TIMEOUT
