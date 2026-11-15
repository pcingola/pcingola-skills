"""One comment of the editor page, as `comments.json` stores it."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .http_error import HttpError
from .kinds import CommentState
from .mark import Mark

MESSAGE_MAX = 10_000
IDS_MAX = 200
ID_MAX = 200


@dataclass(frozen=True)
class CommentInput:
    """The body of `POST /api/comment`: `{t, chapter, mark, ids, message}`."""

    t: float
    chapter: str | None
    mark: Mark
    ids: list[str]
    message: str

    @classmethod
    def from_json(cls, body: object) -> CommentInput:
        """The checked body; 400 for a missing or wrong field."""
        if not isinstance(body, dict):
            raise HttpError(400, "the body must be a JSON object")
        t = body.get("t")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
            raise HttpError(400, "t must be a number of seconds, 0 or more")
        chapter = body.get("chapter")
        if chapter is not None and (not isinstance(chapter, str) or len(chapter) > ID_MAX):
            raise HttpError(400, "chapter must be a chapter id or null")
        ids = body.get("ids", [])
        if (not isinstance(ids, list) or len(ids) > IDS_MAX
                or not all(isinstance(i, str) and 0 < len(i) <= ID_MAX for i in ids)):
            raise HttpError(400, "ids must be a list of element ids")
        message = body.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > MESSAGE_MAX:
            raise HttpError(400, f"message must be a non-empty text of at most {MESSAGE_MAX} characters")
        return cls(float(t), chapter, Mark.from_json(body.get("mark")), list(ids), message.strip())


@dataclass
class Comment:
    """`png` is the absolute path of `marks/<id>.png`; `created` an ISO time; `answer` the agent's last post."""

    id: str
    t: float
    chapter: str | None
    mark: Mark
    ids: list[str]
    message: str
    png: str
    created: str
    state: CommentState = CommentState.OPEN
    answer: str | None = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id, "t": self.t, "chapter": self.chapter, "mark": self.mark.to_json(), "ids": self.ids,
            "message": self.message, "png": self.png, "state": self.state.value, "answer": self.answer,
            "created": self.created, **self.extra,
        }

    @classmethod
    def from_json(cls, value: dict) -> Comment:
        """A stored comment; keys the server does not know are kept in `extra` and written back."""
        known = {"id", "t", "chapter", "mark", "ids", "message", "png", "state", "answer", "created"}
        return cls(
            id=str(value["id"]), t=float(value["t"]), chapter=value.get("chapter"),
            mark=Mark.from_json(value["mark"]), ids=list(value.get("ids") or []), message=str(value["message"]),
            png=str(value.get("png") or ""), created=str(value.get("created") or ""),
            state=CommentState(value.get("state", CommentState.OPEN.value)), answer=value.get("answer"),
            extra={k: v for k, v in value.items() if k not in known},
        )
