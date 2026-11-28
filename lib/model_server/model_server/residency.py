"""`Residency`: which in-process models are loaded, keep-alive, and room in memory before a load.

Keep-alive: an in-process model stays loaded `keep_alive` seconds after its last request ends, then `sweep`
unloads it (`ai_models.local.unload_model`); with `keep_alive` 0 it unloads when its last request ends.

Room: before the first request of an in-process model that is not loaded (`begin`), the free memory is read
(`free_bytes`: the GPU's for the GPU kinds, the system's available memory for the CPU kinds) and compared with the
model's `memory`. A model larger than the total memory (`total_bytes`) is refused at once with HTTP 507. While the
free memory is short, the idle in-process models are unloaded, least recently used first, then the models Ollama
holds (`GET /api/ps`, then `keep_alive: 0`), each followed by a wait for the memory to come back (`_settle`: until it
suffices, stops growing for `SETTLE_STABLE_SECONDS`, or `SETTLE_SECONDS` pass). When it is still short, the request
fails with HTTP 507. A GPU model without `memory`
first unloads every idle in-process GPU model, and the load's own weight check (`ai_models.local.check_memory`)
applies. Before a request to an Ollama model that Ollama does not hold, idle in-process models are unloaded while
the free memory is below the model's size in `GET /api/tags`; Ollama's own models are left to Ollama.

The scheduler runs one model at a time, so the models `begin` unloads are idle; a model a request is using is never
unloaded (`_in_use`).
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .model_ref import GB, ModelRef
from .ollama import Ollama
from .server_error import ErrorType, ServerError

SETTLE_SECONDS = 10.0
SETTLE_STABLE_SECONDS = 2.0
SETTLE_POLL_SECONDS = 0.5
SWEEP_SECONDS = 1.0


def free_bytes(gpu: bool) -> int:
    """The free memory a model of a GPU kind (`gpu`) or a CPU kind loads into (`ai_models.local.free_memory`)."""
    from ai_models import AIModelsError, local

    if gpu:
        try:
            return local.free_memory(local.device())
        except AIModelsError:
            pass
    return local.free_memory("cpu")


def total_bytes(gpu: bool) -> int:
    """The total memory a model of a GPU kind (`gpu`) or a CPU kind loads into: CUDA's device memory, MPS's
    recommended maximum, else the system's memory."""
    import psutil

    if gpu:
        from ai_models import AIModelsError, local

        try:
            dev = local.device()
        except AIModelsError:
            dev = "cpu"
        if dev in ("cuda", "mps"):
            import torch

            return torch.cuda.mem_get_info()[1] if dev == "cuda" else torch.mps.recommended_max_memory()
    return psutil.virtual_memory().total


@dataclass
class Loaded:
    """An in-process model this server has run: its ref and when its last request ended (`time.monotonic`)."""

    ref: ModelRef
    last: float


class Residency:
    """The in-process models of one server; every method runs on the server's event loop."""

    def __init__(self, keep_alive: float, weights_dir: Path | None, ollama: Ollama) -> None:
        self.keep_alive = keep_alive
        self.weights_dir = weights_dir
        self.ollama = ollama
        self.loaded: dict[str, Loaded] = {}
        self._in_use: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    def idle(self) -> list[Loaded]:
        """The loaded models no request uses, least recently used first."""
        return sorted((m for m in self.loaded.values() if not self._in_use[m.ref.id]), key=lambda m: m.last)

    async def begin(self, ref: ModelRef) -> None:
        """Before a request to `ref`: make room for it when it is not loaded (module docstring) and mark it in use.
        `ServerError` 507 when it does not fit."""
        async with self._lock:
            if not ref.local:
                await self._room_for_ollama(ref)
                return
            if ref.id not in self.loaded:
                await self._room_for(ref)
                self.loaded[ref.id] = Loaded(ref, time.monotonic())
            self._in_use[ref.id] += 1

    async def end(self, ref: ModelRef) -> None:
        """After a request to `ref`: record its end; unload it now when `keep_alive` is 0 and no request uses it."""
        if not ref.local:
            return
        async with self._lock:
            self._in_use[ref.id] -= 1
            if ref.id in self.loaded:
                self.loaded[ref.id].last = time.monotonic()
            if self.keep_alive == 0 and not self._in_use[ref.id]:
                await self._unload(ref.id)

    async def sweep(self) -> list[str]:
        """Unload the idle models whose last request ended `keep_alive` seconds ago or more; their ids."""
        async with self._lock:
            now = time.monotonic()
            due = [m.ref.id for m in self.idle() if now - m.last >= self.keep_alive]
            for model_id in due:
                await self._unload(model_id)
            return due

    async def run(self) -> None:
        """`sweep` every `SWEEP_SECONDS` (at most every `keep_alive` seconds), until cancelled."""
        while True:
            await asyncio.sleep(min(SWEEP_SECONDS, self.keep_alive) or SWEEP_SECONDS)
            await self.sweep()

    async def unload_all(self) -> None:
        """Unload every model this process holds (`ai_models.local.unload`), at shutdown."""
        from ai_models import local

        async with self._lock:
            await asyncio.to_thread(local.unload)
            self.loaded.clear()

    async def _unload(self, model_id: str) -> None:
        from ai_models import local

        await asyncio.to_thread(local.unload_model, model_id, self.weights_dir)
        self.loaded.pop(model_id, None)

    async def _settle(self, gpu: bool, need: int) -> int:
        """The free memory, read every `SETTLE_POLL_SECONDS` until it reaches `need`, has not grown for
        `SETTLE_STABLE_SECONDS`, or `SETTLE_SECONDS` pass."""
        start = time.monotonic()
        best, grew = -1, start
        while (free := await asyncio.to_thread(free_bytes, gpu)) < need:
            now = time.monotonic()
            if free > best:
                best, grew = free, now
            if now - start >= SETTLE_SECONDS or now - grew >= SETTLE_STABLE_SECONDS:
                break
            await asyncio.sleep(SETTLE_POLL_SECONDS)
        return free

    async def _room_for(self, ref: ModelRef) -> None:
        need = ref.memory
        if need is None:
            if ref.gpu:
                for m in self.idle():
                    if m.ref.gpu:
                        await self._unload(m.ref.id)
            return
        where = f"`memory` of providers.{ref.provider}.models.{ref.name}"
        total = await asyncio.to_thread(total_bytes, ref.gpu)
        if need > total:
            raise ServerError(507, f"{ref.id} takes {need / GB:g} GB at its peak ({where}), more than the "
                              f"{total / GB:.1f} GB of the device", ErrorType.INSUFFICIENT_MEMORY,
                              "insufficient_memory")
        free = await asyncio.to_thread(free_bytes, ref.gpu)
        for m in self.idle():
            if free >= need:
                return
            await self._unload(m.ref.id)
            free = await self._settle(ref.gpu, need)
        for resident in await self.ollama.resident():
            if free >= need:
                return
            await self.ollama.unload(resident.name)
            free = await self._settle(ref.gpu, need)
        if free < need:
            raise ServerError(507, f"{ref.id} takes {need / GB:g} GB at its peak ({where}) and {free / GB:.1f} GB "
                              "are free after unloading every idle model", ErrorType.INSUFFICIENT_MEMORY,
                              "insufficient_memory")

    async def _room_for_ollama(self, ref: ModelRef) -> None:
        if any(r.name in (ref.tag, f"{ref.tag}:latest") for r in await self.ollama.resident()):
            return
        need = await self.ollama.size(ref.tag)
        if need is None or not self.loaded:
            return
        free = await asyncio.to_thread(free_bytes, True)
        for m in self.idle():
            if free >= need:
                return
            await self._unload(m.ref.id)
            free = await self._settle(True, need)
