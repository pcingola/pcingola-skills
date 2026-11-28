"""The cancel signal of an in-process model call: a `threading.Event` that a caller (the model server) sets to stop a
call running in another thread.

`signal(event)` makes `event` the signal of the calls the block makes, through a context variable. `asyncio.to_thread`
copies the context into its worker thread, so the calls of `aspeak`, `acompose`, `aanimate`, `apresent` and
`DiffusersImageModel.generate` started in the block see it. `check` raises `Cancelled` when the signal is set; the
runtimes call it where control returns to this package (docs/ai_models.md, Cancellation):

    diffusers   before the pipeline call, then at the end of each denoising step: `callback_on_step_end` when the
                pipeline's `__call__` takes it, else a forward pre-hook on its `transformer` or `unet` (`stoppable`)
    chatterbox  before the synthesis, then before each forward of the T3 transformer (one per speech token, `hooked`)
    fish        before each span and after each chunk `generate_long` yields
    kokoro      before `Kokoro.create` only: kokoro-onnx runs its batches without returning to the caller
    torchaudio  before the acoustic model and before the forced alignment (`Aligner.align`)

Without a signal (a skill calling `ai_models` in its own process), `check` does nothing and no hook or callback is
added, so the calls run as before.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from typing import Any

from .errors import Cancelled

__all__ = ["Cancelled", "active", "check", "hooked", "on_step_end", "signal", "stoppable"]

_signal: ContextVar[threading.Event | None] = ContextVar("ai_models_cancel", default=None)
# The pipeline components a denoising step calls once per step, for the pipelines without `callback_on_step_end`.
DENOISERS = ("transformer", "unet")


@contextmanager
def signal(event: threading.Event) -> Iterator[threading.Event]:
    """`event` is the cancel signal of the model calls of the block and of the worker threads it starts with
    `asyncio.to_thread`."""
    token = _signal.set(event)
    try:
        yield event
    finally:
        _signal.reset(token)


def active() -> bool:
    """Whether the current context has a cancel signal."""
    return _signal.get() is not None


def check() -> None:
    """`Cancelled` when the current context's signal is set; nothing without a signal."""
    event = _signal.get()
    if event is not None and event.is_set():
        raise Cancelled("the request was cancelled")


def on_step_end(pipe: Any, step: int, timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
    """A diffusers `callback_on_step_end`: `check`, then the tensors unchanged."""
    check()
    return callback_kwargs


def _pre_hook(module: Any, args: Any) -> None:
    check()


@contextmanager
def hooked(*modules: Any) -> Iterator[None]:
    """A forward pre-hook that runs `check` on each torch module of `modules` for the block, when the context has a
    signal; the hooks are removed after the block. The hook reads the signal of the thread that calls the module."""
    with ExitStack() as stack:
        if active():
            for m in modules:
                if m is not None:
                    stack.callback(m.register_forward_pre_hook(_pre_hook).remove)
        yield


@contextmanager
def stoppable(pipe: Any, kwargs: dict[str, Any]) -> Iterator[None]:
    """Make the diffusers pipeline call of the block stop at the end of a step when the signal is set: `check` now,
    then `on_step_end` as `callback_on_step_end` in `kwargs` when `pipe.__call__` takes it and the caller passes none,
    else a forward pre-hook on the pipeline's denoiser (`DENOISERS`; a `ModularPipeline` takes no callback). Nothing
    without a signal."""
    if not active():
        yield
        return
    check()
    if "callback_on_step_end" in inspect.signature(pipe.__call__).parameters and "callback_on_step_end" not in kwargs:
        kwargs["callback_on_step_end"] = on_step_end
        yield
        return
    components = getattr(pipe, "components", None) or {}
    with hooked(*(components.get(name) for name in DENOISERS)):
        yield
