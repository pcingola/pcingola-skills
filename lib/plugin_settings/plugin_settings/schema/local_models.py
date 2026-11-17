"""`local_models:`: how a process waits for the lock of the local models (`ai_models.local.hold_lock`)."""

from __future__ import annotations

from pydantic import PositiveFloat

from .base import Strict


class LocalModels(Strict):
    """`lock_wait`: the seconds a process waits for another process that holds the local models before it fails
    with an error naming that process. Unset: it waits until the other process exits."""

    lock_wait: PositiveFloat | None = None
