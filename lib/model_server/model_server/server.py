"""`Server`: the state of one model server: its settings, the scheduler and its jobs, the in-process models, Ollama,
the video jobs and the reference recordings of speech requests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import plugin_settings
from plugin_settings import Config, ModelServerSettings

from .job import Job, cancelled_error
from .lease import Lease
from .model_ref import ModelRef
from .model_role import ModelRole
from .ollama import Ollama
from .references import References
from .residency import Residency
from .scheduler import Scheduler
from .server_error import ServerError
from .video_jobs import VideoJobs


class Server:
    """The server of the settings `settings` (`model_server` of the config at start). The models are read from the
    config file at each request (`config`), as `ai_models` reads them."""

    def __init__(self, settings: ModelServerSettings) -> None:
        self.settings = settings
        self.scheduler = Scheduler()
        self.ollama = Ollama(settings.ollama_url, settings.timeout)
        self.residency = Residency(settings.keep_alive, settings.weights_dir, self.ollama)
        self.videos = VideoJobs(settings.video_ttl)
        self.references = References()
        self._tasks: set[asyncio.Task] = set()

    def config(self) -> Config:
        """The config file, validated (`plugin_settings.load_config`); `ServerError` 500 when it is not valid."""
        try:
            return plugin_settings.load_config()
        except plugin_settings.ConfigFileError as e:
            raise ServerError(500, str(e)) from None

    def ref(self, model: object, *roles: ModelRole) -> ModelRef:
        """The `ModelRef` of a request's `model`; with `roles`, a local model of one of them (`ModelRef.require`)."""
        ref = ModelRef.parse(model, self.config())
        return ref.require(*roles) if roles else ref

    def submit(self, ref: ModelRef, job_id: str | None = None, role: ModelRole | None = None) -> Job:
        """A new queued job of `ref` (`Scheduler.submit`), of `role`, else of the model's role."""
        return self.scheduler.submit(ref.id, ref.parallel, role or ref.role, job_id)

    async def admit(self, ref: ModelRef, job: Job | None = None) -> Lease:
        """A scheduler slot for the job `job` of `ref` (a new one when None) with room made for it
        (`Residency.begin`); the caller ends it with `finish`. `cancelled_error` when the job is cancelled before
        it runs."""
        lease = await self.scheduler.acquire(job or self.submit(ref))
        try:
            if lease.job.cancelled:
                raise cancelled_error(lease.job.id)
            await self.residency.begin(ref)
        except BaseException:
            lease.release()
            raise
        return lease

    async def finish(self, ref: ModelRef, lease: Lease) -> None:
        try:
            await self.residency.end(ref)
        finally:
            lease.release()

    @asynccontextmanager
    async def running(self, ref: ModelRef, job: Job | None = None) -> AsyncIterator[Job]:
        """Run the block as the job `job` of `ref` (a new one when None): admitted by the scheduler, with room made
        in memory, the job's signal the `ai_models.cancel` signal of the block's in-process calls. A cancelled job
        raises `cancelled_error`: when its call stops with `ai_models.Cancelled`, and when it returns after the
        cancel (its result is discarded). The slot is released once the block ends."""
        from ai_models import Cancelled, cancel

        lease = await self.admit(ref, job)
        try:
            with cancel.signal(lease.job.signal):
                yield lease.job
            if lease.job.cancelled:
                raise cancelled_error(lease.job.id)
        except Cancelled:
            raise cancelled_error(lease.job.id) from None
        finally:
            await self.finish(ref, lease)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Run `coro` as a task this server keeps until it ends (a video job, the keep-alive sweep)."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def start(self) -> None:
        self.spawn(self.residency.run())

    async def stop(self) -> None:
        """Cancel the tasks, unload every model, close the Ollama client and remove the reference recordings."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.residency.unload_all()
        await self.ollama.aclose()
        self.references.close()
