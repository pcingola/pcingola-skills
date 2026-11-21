"""`Scheduler`: one model runs at a time.

A request asks for a slot of its model (`acquire`). It is admitted at once when no request runs, or when the running
requests are of the same model, that model runs requests in parallel (`parallel`) and no request waits. Otherwise it
waits in one FIFO queue. When the last running request ends, the head of the queue starts, with every request
behind it of the same model while that model runs in parallel. A request for the running model that arrives while
another model waits queues behind it, so a stream of requests for one model does not starve the others.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

from .lease import Lease


@dataclass
class _Waiter:
    model: str
    parallel: bool
    future: asyncio.Future = field(repr=False)


@dataclass(frozen=True)
class SchedulerState:
    """A snapshot: the running model (None when idle), how many of its requests run, and the models waiting, in
    order."""

    active: str | None
    running: int
    waiting: tuple[str, ...]


class Scheduler:
    """The slots of the requests of one server; every method runs on the server's event loop."""

    def __init__(self) -> None:
        self._active: str | None = None
        self._parallel = False
        self._running = 0
        self._queue: deque[_Waiter] = deque()

    def state(self) -> SchedulerState:
        return SchedulerState(self._active, self._running, tuple(w.model for w in self._queue))

    def _admissible(self, model: str, parallel: bool) -> bool:
        return self._running == 0 or (model == self._active and parallel and self._parallel)

    def _start(self, model: str, parallel: bool) -> Lease:
        self._active, self._parallel = model, parallel
        self._running += 1
        return Lease(model, self._release)

    async def acquire(self, model: str, parallel: bool) -> Lease:
        """A `Lease` for one request to `model`, after waiting for its turn (module docstring). A waiter that is
        cancelled leaves the queue; one cancelled after it was admitted releases its slot."""
        if not self._queue and self._admissible(model, parallel):
            return self._start(model, parallel)
        waiter = _Waiter(model, parallel, asyncio.get_running_loop().create_future())
        self._queue.append(waiter)
        try:
            return await waiter.future
        except asyncio.CancelledError:
            if waiter.future.done() and not waiter.future.cancelled():
                waiter.future.result().release()
            else:
                self._queue.remove(waiter)
                self._dispatch()
            raise

    def _release(self) -> None:
        self._running -= 1
        if self._running == 0:
            self._active = None
        self._dispatch()

    def _dispatch(self) -> None:
        """Start the head of the queue while it is admissible."""
        while self._queue and self._admissible(self._queue[0].model, self._queue[0].parallel):
            waiter = self._queue.popleft()
            waiter.future.set_result(self._start(waiter.model, waiter.parallel))
