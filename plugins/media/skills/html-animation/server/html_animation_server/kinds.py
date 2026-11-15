"""The fixed sets of names the server reads and writes."""

from __future__ import annotations

from enum import StrEnum


class LineType(StrEnum):
    """Types of the JSON lines on stdout (server to mod)."""

    READY = "ready"
    REQUEST = "request"
    STOP = "stop"


class AgentType(StrEnum):
    """Types of the messages from the mod, on stdin or `POST /api/agent`."""

    POST = "post"
    NOTE = "note"
    DONE = "done"


class EventKind(StrEnum):
    """Names of the server-sent events to the editor page."""

    CHANGE = "change"
    POST = "post"
    NOTE = "note"
    COMMENT = "comment"


class CommentState(StrEnum):
    OPEN = "open"
    DONE = "done"


class MarkKind(StrEnum):
    POINT = "point"
    RECT = "rect"
