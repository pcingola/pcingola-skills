"""`JobState`: where a job of the scheduler is."""

from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    """A job waits in the scheduler's queue (`queued`) or holds a slot (`running`); a job that ends leaves the list."""

    QUEUED = "queued"
    RUNNING = "running"
