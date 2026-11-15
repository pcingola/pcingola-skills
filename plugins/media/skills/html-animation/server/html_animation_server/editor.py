"""State shared by the request handlers and the background loops of one editor server."""

from __future__ import annotations

import collections
import json
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TextIO

from .cli import AnimationCli
from .comment import Comment, CommentInput
from .comment_store import CommentStore
from .folder import AnimationFolder
from .http_error import HttpError
from .kinds import AgentType, EventKind, LineType
from .log import log
from .prompt import comment_prompt

PAGE_DIR = Path(__file__).resolve().parents[1] / "page"
POLL_INTERVAL = 0.5
# The agent's posts and notes kept for a page that connects later.
MESSAGES_MAX = 200
TEXT_MAX = 20_000


def stdout_emit(line: dict) -> None:
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()


class Editor:
    def __init__(self, folder: str | Path, cli: AnimationCli | None = None, page_dir: str | Path = PAGE_DIR,
                 emit: Callable[[dict], None] = stdout_emit) -> None:
        self.folder = AnimationFolder(folder)
        self.store = CommentStore(self.folder.comments_file)
        self.cli = cli or AnimationCli()
        self.page_dir = Path(page_dir).resolve()
        self.emit = emit
        self.lock = threading.Lock()
        # One render at a time: each still starts a headless Chromium.
        self.render_lock = threading.Lock()
        self.clients: list[queue.Queue] = []
        self.messages: collections.deque[dict] = collections.deque(maxlen=MESSAGES_MAX)
        # The last post of each comment the agent works on, stored as its answer on `done`.
        self.last_post: dict[str, str] = {}
        # The comment whose request was sent last, for a post that names none.
        self.current: str | None = None
        self.mtime = self.folder.index_mtime()
        self.httpd: ThreadingHTTPServer | None = None
        self.url: str | None = None
        # Comments the user stopped in this server's life; they stay open in comments.json.
        self.stopped: set[str] = set()

    # Page events

    def connect(self) -> queue.Queue:
        client: queue.Queue = queue.Queue()
        with self.lock:
            self.clients.append(client)
        return client

    def disconnect(self, client: queue.Queue) -> None:
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)

    def broadcast(self, kind: EventKind, data: dict) -> None:
        event = {"kind": kind.value, **data}
        with self.lock:
            for client in self.clients:
                client.put(event)

    # State

    def state(self) -> dict:
        return {
            "animation": self.folder.animation(),
            "comments": [self.view(c) for c in self.store.load()],
            "version": self.folder.version(),
            "mtime": self.folder.index_mtime(),
            "folder": str(self.folder.root),
            "messages": list(self.messages),
        }

    # Comments

    def add_comment(self, body: object) -> Comment:
        """The marked still, the stored comment, then the `request` line for the mod. The agent takes the snapshot
        itself before its first edit, so a comment queued behind another starts from that one's result."""
        given = CommentInput.from_json(body)
        comment_id = CommentStore.new_id()
        png = self.folder.marks_dir / f"{comment_id}.png"
        with self.render_lock:
            self.folder.marks_dir.mkdir(exist_ok=True)
            self.cli.still(self.folder.root, given.t, given.mark, png)
            comment = self.store.append(comment_id, given, png)
        self.current = comment.id
        self.broadcast(EventKind.COMMENT, {"comment": self.view(comment)})
        self.emit({"type": LineType.REQUEST.value, "id": comment.id,
                   "prompt": comment_prompt(comment, self.folder.root)})
        return comment

    def view(self, comment: Comment) -> dict:
        """A comment as the page gets it: the stored fields and whether the user stopped it."""
        return {**comment.to_json(), "stopped": comment.id in self.stopped}

    def stop(self, comment_id: str | None) -> None:
        """The `stop` line for the mod: of one comment (queued or running), or with no id of the running one."""
        line: dict = {"type": LineType.STOP.value}
        if comment_id:
            line["id"] = comment_id
            self.stopped.add(comment_id)
            comment = next((c for c in self.store.load() if c.id == comment_id), None)
            if comment is not None:
                self.broadcast(EventKind.COMMENT, {"comment": self.view(comment)})
        self.emit(line)

    # Messages from the mod

    def agent_message(self, value: object) -> None:
        """One `post`, `note` or `done` message from the mod; 400 when it is none of them."""
        if not isinstance(value, dict):
            raise HttpError(400, "a message must be a JSON object")
        try:
            kind = AgentType(value.get("type"))
        except ValueError:
            raise HttpError(400, f"unknown message type: {value.get('type')!r}") from None
        given_id = value.get("id")
        comment_id = given_id if isinstance(given_id, str) and given_id else self.current
        if kind is AgentType.DONE:
            if not comment_id:
                raise HttpError(400, "done needs an id")
            comment = self.store.mark_done(comment_id, self.last_post.pop(comment_id, None))
            if comment is None:
                raise HttpError(404, f"no comment {comment_id}")
            self.broadcast(EventKind.COMMENT, {"comment": self.view(comment)})
            return
        text = str(value.get("text") or "")[:TEXT_MAX]
        message: dict = {"kind": kind.value, "id": comment_id, "text": text, "time": time.time()}
        if kind is AgentType.POST:
            images = value.get("images") if isinstance(value.get("images"), list) else []
            message["images"] = [{"path": str(p), "url": self.folder.url_of(str(p))} for p in images]
            if comment_id:
                self.last_post[comment_id] = text
        with self.lock:
            self.messages.append(message)
        self.broadcast(EventKind(kind.value), {k: v for k, v in message.items() if k != "kind"})

    # Loops

    def poll_index(self) -> None:
        """One check of `index.html`'s mtime; a change is sent to the pages as `change`."""
        mtime = self.folder.index_mtime()
        if mtime != self.mtime:
            self.mtime = mtime
            self.broadcast(EventKind.CHANGE, {"mtime": mtime, "version": self.folder.version()})

    def watch_index(self, interval: float = POLL_INTERVAL) -> None:
        while True:
            try:
                self.poll_index()
            except OSError as e:
                log(f"html-animation server: watch failed: {e}")
            time.sleep(interval)

    def read_stdin(self, stream: TextIO) -> None:
        """Reads JSON lines from the mod until end of file; a bad line is logged and skipped."""
        for text in stream:
            text = text.strip()
            if not text:
                continue
            try:
                self.agent_message(json.loads(text))
            except (ValueError, HttpError) as e:
                log(f"html-animation server: stdin line refused ({e}): {text[:200]}")


def parent_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(parent_pid: int | None, exit_fn: Callable[[int], None], interval: float = 1.0) -> None:
    """Exits when this process's parent id changes or `parent_pid` (the process that started the wrapper; uv run
    sits between it and Python) is gone. macOS and Linux only."""
    first = os.getppid()
    while True:
        if os.getppid() != first or (parent_pid and not parent_alive(parent_pid)):
            log("html-animation server: parent process ended")
            exit_fn(0)
            return
        time.sleep(interval)


def start_loops(editor: Editor, parent_pid: int | None = None, exit_fn: Callable[[int], None] = os._exit) -> None:
    loops: list[tuple[Callable, tuple]] = [(editor.watch_index, ()), (editor.read_stdin, (sys.stdin,))]
    if sys.platform != "win32":
        loops.append((watch_parent, (parent_pid, exit_fn)))
    for target, args in loops:
        threading.Thread(target=target, args=args, daemon=True).start()
