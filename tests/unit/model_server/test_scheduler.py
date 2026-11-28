"""`model_server.scheduler.Scheduler`: one model at a time, parallel requests where the model allows them, one FIFO
queue (docs/model_server.md, Scheduling). Each test runs its requests as tasks on one event loop; no model runs."""

import asyncio

import pytest

from model_server.job_state import JobState
from model_server.scheduler import Scheduler
from model_server.server_error import ServerError


def acquire(s: Scheduler, model: str, parallel: bool):
    """`Scheduler.acquire` of a new job of `model`."""
    return s.acquire(s.submit(model, parallel))


async def settle() -> None:
    """Let the started tasks run up to their next wait."""
    for _ in range(5):
        await asyncio.sleep(0)


def test_parallel_model_admits_together_and_serial_waits():
    """Requests to a parallel model (Ollama) all run at once; a serial model's second request waits for the first."""
    async def main():
        s = Scheduler()
        a, b = await acquire(s, "o", True), await acquire(s, "o", True)
        assert s.state().running == 2 and s.state().active == "o"
        a.release()
        b.release()
        assert s.state().active is None
        first = await acquire(s, "img", False)
        second = asyncio.create_task(acquire(s, "img", False))
        await settle()
        assert not second.done() and s.state().waiting == ("img",)
        first.release()
        await settle()
        assert second.done() and s.state().running == 1
        second.result().release()

    asyncio.run(main())


def test_other_model_waits_and_queue_is_fifo():
    """A request for another model waits until the running requests end; a later request for the running model
    queues behind it, so the waiting model starts first, then the parallel requests behind it start together."""
    async def main():
        s = Scheduler()
        running = await acquire(s, "o", True)
        img = asyncio.create_task(acquire(s, "img", False))
        late = [asyncio.create_task(acquire(s, "o", True)) for _ in range(2)]
        await settle()
        assert s.state().waiting == ("img", "o", "o") and not img.done()
        running.release()
        await settle()
        assert img.done() and not any(t.done() for t in late) and s.state().active == "img"
        img.result().release()
        await settle()
        assert all(t.done() for t in late) and s.state().running == 2 and s.state().active == "o"
        for t in late:
            t.result().release()
        assert s.state().running == 0

    asyncio.run(main())


def test_cancelled_waiter_leaves_the_queue_and_release_is_once():
    """A waiter cancelled before its turn leaves the queue and the one behind it starts in its place; a lease
    released twice frees one slot."""
    async def main():
        s = Scheduler()
        held = await acquire(s, "a", False)
        b = asyncio.create_task(acquire(s, "b", False))
        c = asyncio.create_task(acquire(s, "a", False))
        await settle()
        b.cancel()
        await settle()
        assert b.cancelled() and s.state().waiting == ("a",)
        held.release()
        held.release()
        await settle()
        assert c.done() and s.state().running == 1
        c.result().release()
        assert s.state() == s.state().__class__(None, 0, ())

    asyncio.run(main())


def test_jobs_are_listed_and_a_queued_cancel_leaves_the_queue():
    """Every request is a listed job, queued or running, until its slot is released. A queued job that is cancelled
    leaves the queue and the list at once, its `acquire` raises the 499 `cancelled` error, and the job behind it
    starts when the running one ends."""
    async def main():
        s = Scheduler()
        held = await acquire(s, "a", False)
        b, c = s.submit("b", False), s.submit("c", False)
        tb, tc = asyncio.create_task(s.acquire(b)), asyncio.create_task(s.acquire(c))
        await settle()
        assert [(j.model, j.state) for j in s.jobs()] == [("a", JobState.RUNNING), ("b", JobState.QUEUED),
                                                         ("c", JobState.QUEUED)]
        assert s.cancel(b.id) is b and b.cancelled
        await settle()
        with pytest.raises(ServerError) as e:
            tb.result()
        assert (e.value.status, e.value.error.code) == (499, "cancelled")
        assert s.state().waiting == ("c",) and [j.model for j in s.jobs()] == ["a", "c"]
        assert s.cancel(b.id) is None
        held.release()
        await settle()
        assert tc.done() and s.state().active == "c"
        tc.result().release()
        assert s.jobs() == []

    asyncio.run(main())


def test_cancel_of_a_running_job_signals_it_and_cancel_all():
    """A running job that is cancelled keeps its slot and stays listed with its signal set and its `on_cancel`
    callbacks run, until its lease is released. `cancel_all` removes the queued jobs first, so none starts, then
    signals the running one."""
    async def main():
        s = Scheduler()
        lease = await acquire(s, "a", False)
        called = []
        lease.job.on_cancel(lambda: called.append(True))
        assert s.cancel(lease.job.id) is lease.job and lease.job.signal.is_set() and called == [True]
        assert s.jobs() == [lease.job] and s.state().running == 1
        lease.release()
        assert s.jobs() == [] and s.state().running == 0
        held = await acquire(s, "a", False)
        waiting = [asyncio.create_task(acquire(s, m, False)) for m in ("b", "c")]
        await settle()
        cancelled = s.cancel_all()
        assert [j.state for j in cancelled] == [JobState.QUEUED, JobState.QUEUED, JobState.RUNNING]
        await settle()
        assert all(isinstance(t.exception(), ServerError) for t in waiting)
        assert held.job.cancelled and s.state().waiting == ()
        held.release()
        assert s.state() == s.state().__class__(None, 0, ()) and s.jobs() == []

    asyncio.run(main())


def test_interruptible_ends_at_a_cancel():
    """`Job.interruptible` answers the awaited result, and raises the 499 `cancelled` error when the job is
    cancelled while it waits; the awaited task is cancelled."""
    async def main():
        s = Scheduler()
        job = (await acquire(s, "o", True)).job
        assert await job.interruptible(asyncio.sleep(0, "x")) == "x"
        slow = asyncio.create_task(job.interruptible(asyncio.sleep(10)))
        await settle()
        job.cancel()
        await settle()
        with pytest.raises(ServerError) as e:
            slow.result()
        assert e.value.error.code == "cancelled"

    asyncio.run(main())
