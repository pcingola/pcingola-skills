"""`model_server.scheduler.Scheduler`: one model at a time, parallel requests where the model allows them, one FIFO
queue (docs/model_server.md, Scheduling). Each test runs its requests as tasks on one event loop; no model runs."""

import asyncio

from model_server.scheduler import Scheduler


async def settle() -> None:
    """Let the started tasks run up to their next wait."""
    for _ in range(5):
        await asyncio.sleep(0)


def test_parallel_model_admits_together_and_serial_waits():
    """Requests to a parallel model (Ollama) all run at once; a serial model's second request waits for the first."""
    async def main():
        s = Scheduler()
        a, b = await s.acquire("o", True), await s.acquire("o", True)
        assert s.state().running == 2 and s.state().active == "o"
        a.release()
        b.release()
        assert s.state().active is None
        first = await s.acquire("img", False)
        second = asyncio.create_task(s.acquire("img", False))
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
        running = await s.acquire("o", True)
        img = asyncio.create_task(s.acquire("img", False))
        late = [asyncio.create_task(s.acquire("o", True)) for _ in range(2)]
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
        held = await s.acquire("a", False)
        b = asyncio.create_task(s.acquire("b", False))
        c = asyncio.create_task(s.acquire("a", False))
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
