"""`Lease`: one admitted request of the `Scheduler`, released once."""

from __future__ import annotations

from collections.abc import Callable


class Lease:
    """A slot of the scheduler for one request; `release` calls `on_release` the first time only, so a stream that
    ends and a cleanup that follows may both release it."""

    def __init__(self, model: str, on_release: Callable[[], None]) -> None:
        self.model = model
        self._on_release: Callable[[], None] | None = on_release

    @property
    def released(self) -> bool:
        return self._on_release is None

    def release(self) -> None:
        if self._on_release is not None:
            fn, self._on_release = self._on_release, None
            fn()
