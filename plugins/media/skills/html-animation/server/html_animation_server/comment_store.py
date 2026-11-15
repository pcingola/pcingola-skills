"""`comments.json` of an animation folder: the list of comments, read and written whole under a lock."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .comment import Comment, CommentInput
from .kinds import CommentState
from .http_error import HttpError
from .log import log


class CommentStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def load(self) -> list[Comment]:
        """The stored comments; an entry that does not parse is skipped with a line on stderr, a missing or
        unreadable file is no comments."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as e:
            log(f"html-animation server: {self.path} is not readable: {e}")
            return []
        comments = []
        for value in data if isinstance(data, list) else []:
            try:
                comments.append(Comment.from_json(value))
            except (KeyError, TypeError, ValueError, HttpError) as e:
                log(f"html-animation server: comment skipped: {e}")
        return comments

    def _save(self, comments: list[Comment]) -> None:
        """Writes the file through a temporary file in the same folder, so a reader never sees half of it."""
        text = json.dumps([c.to_json() for c in comments], indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".comments-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def new_id() -> str:
        return "c" + uuid.uuid4().hex[:10]

    def append(self, comment_id: str, given: CommentInput, png: Path) -> Comment:
        comment = Comment(
            id=comment_id, t=given.t, chapter=given.chapter, mark=given.mark, ids=given.ids, message=given.message,
            png=str(png), created=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        with self.lock:
            comments = self.load()
            comments.append(comment)
            self._save(comments)
        return comment

    def mark_done(self, comment_id: str, answer: str | None) -> Comment | None:
        """Sets the comment's state to done and, when given, its answer; None when no comment has that id."""
        with self.lock:
            comments = self.load()
            for comment in comments:
                if comment.id == comment_id:
                    comment.state = CommentState.DONE
                    if answer is not None:
                        comment.answer = answer
                    self._save(comments)
                    return comment
        return None
