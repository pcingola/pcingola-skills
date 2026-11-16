"""`comments/<scene>/comments.json` of a short-video project: the `mark-scene` requests on a scene, oldest first.

Each entry is `{"request", "t", "mark", "ids", "text", "marked", "state"}`; `state` is `open` until the mod reports
the request's turn ended with the agent's answer (`done`) or the user stopped the request (`stopped`).
"""

from __future__ import annotations

import json
import threading
from enum import Enum
from pathlib import Path

from .paths import log, read_json, write_atomic
from .video import COMMENTS, DIRECTORY

COMMENTS_JSON = "comments.json"


class CommentState(str, Enum):
    OPEN = "open"
    DONE = "done"
    STOPPED = "stopped"


class CommentStore:
    """Appends comments and sets their state. The file of each request appended by this server run is remembered;
    another request's file is found by scanning `<root>/short-video/*/comments/*/comments.json`, so a `done` or
    `stopped` after a server restart still reaches its comment."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()
        self.files: dict[str, Path] = {}

    @staticmethod
    def _read(path: Path) -> list:
        data = read_json(path)
        return data if isinstance(data, list) else []

    def _write(self, path: Path, comments: list) -> None:
        write_atomic(path, (json.dumps(comments, indent=2, ensure_ascii=False) + "\n").encode())

    def append(self, directory: Path, request: dict) -> Path:
        """Adds the comment of a checked `mark-scene` request to `directory/comments.json`."""
        path = directory / COMMENTS_JSON
        entry = {"request": request["id"], "t": request["t"], "mark": request["mark"], "ids": request["ids"],
                 "text": request["text"], "marked": request["marked"], "state": CommentState.OPEN.value}
        with self.lock:
            self._write(path, [*self._read(path), entry])
            self.files[request["id"]] = path
        return path

    def _find(self, request_id: str) -> Path | None:
        """The comments.json holding the comment of `request_id`: remembered, else found by a scan."""
        path = self.files.get(request_id)
        if path is not None:
            return path
        for candidate in sorted(self.root.glob(f"{DIRECTORY}/*/{COMMENTS}/*/{COMMENTS_JSON}")):
            if candidate.is_symlink():
                continue
            if any(isinstance(c, dict) and c.get("request") == request_id for c in self._read(candidate)):
                self.files[request_id] = candidate
                return candidate
        return None

    def mark(self, request_id: object, state: CommentState) -> bool:
        """Sets the state of the open comment of `request_id`; False when no comments.json holds it."""
        if not isinstance(request_id, str) or not request_id:
            return False
        with self.lock:
            path = self._find(request_id)
            if path is None:
                return False
            comments = self._read(path)
            for c in comments:
                if isinstance(c, dict) and c.get("request") == request_id and c.get("state") == CommentState.OPEN:
                    c["state"] = state.value
            try:
                self._write(path, comments)
            except OSError as e:
                log(f"studio server: cannot write {path}: {e}")
                return False
        return True
