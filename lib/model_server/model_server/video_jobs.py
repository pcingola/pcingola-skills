"""`VideoJobs`: the video jobs of one server, kept until they expire."""

from __future__ import annotations

import time

from .server_error import ErrorType, ServerError
from .video_job import VideoJob


class VideoJobs:
    """The jobs by id; a job that ended more than `ttl` seconds ago is dropped at the next lookup."""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._jobs: dict[str, VideoJob] = {}

    def add(self, job: VideoJob) -> VideoJob:
        self._expire()
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> VideoJob:
        """The job `job_id`; `ServerError` 404 when there is none or it expired."""
        self._expire()
        job = self._jobs.get(job_id)
        if job is None:
            raise ServerError(404, f"no video {job_id!r} (unknown, or expired {self.ttl:g} s after it ended)",
                              ErrorType.NOT_FOUND, "video_not_found", "video_id")
        return job

    def _expire(self) -> None:
        now = time.time()
        for job_id in [j.id for j in self._jobs.values() if j.expires_at is not None and j.expires_at <= now]:
            del self._jobs[job_id]
