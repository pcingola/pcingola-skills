"""`JobInfo`: a job of the scheduler as `GET /v1/jobs` and `DELETE /v1/jobs` answer it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .job_state import JobState


class JobInfo(BaseModel):
    """One job: its id (a video job's is the video's id), model id, role (None for an Ollama model whose role Ollama
    did not answer), state, when it was created and when it started (Unix seconds; `started_at` None while queued),
    and whether a cancel was asked (`cancelled`: a running job stays listed until its call stops)."""

    object: Literal["job"] = "job"
    id: str
    model: str
    role: str | None
    state: JobState
    created_at: float
    started_at: float | None
    cancelled: bool
