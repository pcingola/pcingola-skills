"""`VideoJob`: one job of `POST /v1/videos`, shown as `openai.types.Video`."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from openai.types import Video
from openai.types.video_create_error import VideoCreateError


class VideoStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VideoJob:
    """A video job: its model, prompt, clip length (seconds, as text) and size (`WxH`), its status, and the MP4 once
    completed. `expires_at` is set when it ends: the job and its file are dropped then."""

    model: str
    prompt: str
    seconds: str
    size: str
    id: str = field(default_factory=lambda: f"video_{uuid.uuid4().hex}")
    created_at: int = field(default_factory=lambda: int(time.time()))
    status: VideoStatus = VideoStatus.QUEUED
    progress: int = 0
    completed_at: int | None = None
    expires_at: int | None = None
    error: VideoCreateError | None = None
    content: bytes | None = field(default=None, repr=False)

    def start(self) -> None:
        self.status = VideoStatus.IN_PROGRESS

    def complete(self, content: bytes, ttl: float) -> None:
        self.content, self.status, self.progress = content, VideoStatus.COMPLETED, 100
        self._end(ttl)

    def fail(self, code: str, message: str, ttl: float) -> None:
        self.error, self.status = VideoCreateError(code=code, message=message), VideoStatus.FAILED
        self._end(ttl)

    def _end(self, ttl: float) -> None:
        self.completed_at = int(time.time())
        self.expires_at = self.completed_at + int(ttl)

    def video(self) -> Video:
        """The job as `openai.types.Video`. Built without validation: `Video` types `size` and `seconds` as the
        values of OpenAI's own models, and a local model makes other sizes and lengths."""
        return Video.model_construct(id=self.id, object="video", model=self.model, prompt=self.prompt,
                                     created_at=self.created_at, completed_at=self.completed_at,
                                     expires_at=self.expires_at, progress=self.progress, seconds=self.seconds,
                                     size=self.size, status=self.status.value, error=self.error,
                                     remixed_from_video_id=None)
