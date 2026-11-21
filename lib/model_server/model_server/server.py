"""`Server`: the state of one model server: its settings, the scheduler, the in-process models, Ollama and the
video jobs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import plugin_settings
from plugin_settings import Config, ModelServerSettings

from .lease import Lease
from .model_ref import ModelRef
from .model_role import ModelRole
from .ollama import Ollama
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

    async def admit(self, ref: ModelRef) -> Lease:
        """A scheduler slot for `ref` with room made for it (`Residency.begin`); the caller ends it with `finish`."""
        lease = await self.scheduler.acquire(ref.id, ref.parallel)
        try:
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
    async def running(self, ref: ModelRef) -> AsyncIterator[None]:
        """Run the block as one request to `ref`: admitted by the scheduler, with room made in memory."""
        lease = await self.admit(ref)
        try:
            yield
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
        """Cancel the tasks, unload every model and close the Ollama client."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.residency.unload_all()
        await self.ollama.aclose()
