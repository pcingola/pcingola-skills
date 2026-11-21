"""`ServedModel`: a local model of a model server, as its `GET /models/{id}` answer describes it (`served`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plugin_settings import ProviderKind, Task


@dataclass(frozen=True)
class ServedModel:
    """The client's model id (`id`), the server's model id (`bare`), the server provider's `kind`, the task the
    model serves (`role`: image, music, video, presenter, speech or align), the validated `entry` and, for a speech
    model, the server's list of its `voices` (None when the answer has none)."""

    id: str
    bare: str
    kind: ProviderKind
    role: Task
    entry: Any
    voices: list[str] | None = None
