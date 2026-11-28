"""`Scheduler`: one model runs at a time, and every request is a `Job` that a client can list and cancel.

A request is submitted as a job (`submit`), listed from then until its slot is released (`jobs`), and asks for its
slot (`acquire`). It is admitted at once when no request runs, or when the running requests are of the same model,
that model runs requests in parallel (`parallel`) and no request waits. Otherwise it waits in one FIFO queue. When
the last running request ends, the head of the queue starts, with every request behind it of the same model while
that model runs in parallel. A request for the running model that arrives while another model waits queues behind
it, so a stream of requests for one model does not starve the others.

`cancel` of a queued job removes it from the queue and the list at once: its `acquire` raises
`job.cancelled_error`, and the queue moves on. `cancel` of a running job sets its signal (`Job.cancel`); the job
stays listed, with `cancelled` true, until its request stops and releases its slot.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass

from .job import Job, cancelled_error
from .job_state import JobState
from .lease import Lease
from .model_role import ModelRole


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
        self._queue: deque[Job] = deque()
        self._jobs: dict[str, Job] = {}

    def state(self) -> SchedulerState:
        return SchedulerState(self._active, self._running, tuple(j.model for j in self._queue))

    def submit(self, model: str, parallel: bool, role: ModelRole | None = None, job_id: str | None = None) -> Job:
        """A new queued job of `model`, listed from now on; its id is `job_id` when given."""
        job = Job(model, parallel, role, **({"id": job_id} if job_id else {}))
        self._jobs[job.id] = job
        return job

    def jobs(self) -> list[Job]:
        """The queued and running jobs, oldest first."""
        return sorted(self._jobs.values(), key=lambda j: j.created_at)

    def cancel(self, job_id: str) -> Job | None:
        """Cancel the job `job_id` (module docstring); None when no such job is queued or running."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.state == JobState.QUEUED:
            del self._jobs[job.id]
            if job in self._queue:
                self._queue.remove(job)
            if job.future is not None and not job.future.done():
                job.future.set_exception(cancelled_error(job.id))
            job.cancel()
            self._dispatch()
        else:
            job.cancel()
        return job

    def cancel_all(self) -> list[Job]:
        """Cancel every job, the queued ones first, so none of them starts when a running one stops."""
        jobs = sorted(self.jobs(), key=lambda j: j.state != JobState.QUEUED)
        return [j for j in jobs if self.cancel(j.id) is not None]

    def _admissible(self, model: str, parallel: bool) -> bool:
        return self._running == 0 or (model == self._active and parallel and self._parallel)

    def _start(self, job: Job) -> Lease:
        self._active, self._parallel = job.model, job.parallel
        self._running += 1
        job.state, job.started_at = JobState.RUNNING, time.time()
        return Lease(job, lambda: self._release(job))

    async def acquire(self, job: Job) -> Lease:
        """A `Lease` for the submitted `job`, after waiting for its turn (module docstring); `cancelled_error` when
        it is cancelled before it starts. A waiter whose task is cancelled leaves the queue; one cancelled after it
        was admitted releases its slot."""
        if job.cancelled:
            self._jobs.pop(job.id, None)
            raise cancelled_error(job.id)
        self._jobs[job.id] = job
        if not self._queue and self._admissible(job.model, job.parallel):
            return self._start(job)
        future = job.future = asyncio.get_running_loop().create_future()
        self._queue.append(job)
        try:
            return await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled() and future.exception() is None:
                future.result().release()
            else:
                if job in self._queue:
                    self._queue.remove(job)
                self._jobs.pop(job.id, None)
                self._dispatch()
            raise
        finally:
            job.future = None

    def _release(self, job: Job) -> None:
        self._jobs.pop(job.id, None)
        self._running -= 1
        if self._running == 0:
            self._active = None
        self._dispatch()

    def _dispatch(self) -> None:
        """Start the head of the queue while it is admissible."""
        while self._queue and self._admissible(self._queue[0].model, self._queue[0].parallel):
            job = self._queue.popleft()
            job.future.set_result(self._start(job))
