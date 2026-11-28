"""`Job`: one request of the scheduler, from its submission until its slot is released, and `cancelled_error`."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from .job_info import JobInfo
from .job_state import JobState
from .model_role import ModelRole
from .server_error import ErrorType, ServerError

T = TypeVar("T")
CANCELLED_STATUS = 499  # the HTTP status of google.rpc.Code CANCELLED; the openai SDK does not retry it


def cancelled_error(job_id: str) -> ServerError:
    """The error of a request whose job was cancelled: 499 `cancelled`."""
    return ServerError(CANCELLED_STATUS, f"job {job_id} was cancelled", ErrorType.CANCELLED, "cancelled")


@dataclass(eq=False)
class Job:
    """A request to `model` (of `role`; `parallel`: the model runs requests in parallel). `signal` is set when the
    job is cancelled; it is the `ai_models.cancel` signal of the job's in-process call, and the callbacks of
    `on_cancel` run when it is set (on the event loop). `future` is the scheduler's, while the job waits."""

    model: str
    parallel: bool
    role: ModelRole | None = None
    id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex}")
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    state: JobState = JobState.QUEUED
    signal: threading.Event = field(default_factory=threading.Event, repr=False)
    future: asyncio.Future | None = field(default=None, repr=False)
    _callbacks: list[Callable[[], None]] = field(default_factory=list, repr=False)

    @property
    def cancelled(self) -> bool:
        return self.signal.is_set()

    def cancel(self) -> None:
        """Set the signal and run the `on_cancel` callbacks, once."""
        if self.cancelled:
            return
        self.signal.set()
        for fn in list(self._callbacks):
            fn()

    def on_cancel(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Run `fn` when the job is cancelled (at once when it is already); the function returned removes it."""
        if self.cancelled:
            fn()
            return lambda: None
        self._callbacks.append(fn)
        return lambda: self._callbacks.remove(fn) if fn in self._callbacks else None

    async def interruptible(self, aw: Awaitable[T]) -> T:
        """The result of `aw`, run as a task that a cancel of the job cancels; `cancelled_error` then. A cancel of
        the calling task (a client that goes away) propagates as `asyncio.CancelledError`."""
        task = asyncio.ensure_future(aw)
        remove = self.on_cancel(task.cancel)
        try:
            return await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if self.cancelled and not (current is not None and current.cancelling()):
                raise cancelled_error(self.id) from None
            raise
        finally:
            remove()

    def info(self) -> JobInfo:
        return JobInfo(id=self.id, model=self.model, role=self.role.value if self.role else None, state=self.state,
                       created_at=self.created_at, started_at=self.started_at, cancelled=self.cancelled)
