"""The studio HTTP server: page, project files, requests to the mod, events to the page.

stdout carries one JSON object per line to the mod (`ready`, `request`, `stop`); stderr is a log.
Requests are accepted only with a `Host` of this server, and POSTs only without an `Origin` (the mod) or with this
server's own origin (the page), so another web page in the browser can neither read project files through a
rebound host name nor send requests.
"""

from __future__ import annotations

import collections
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from .catalogue import read_catalogue
from .deck import ASSEMBLY, slide_images, versions_of
from .models import read_models
from .paths import (IMAGE_SUFFIXES, HttpError, decode_data_url, inside, log, png_size, positive, read_json,
                    resolve_abs, safe_name, slug, write_atomic, write_new)
from .trash import move_to_trash
from .projects import (AUTONOMY, NAME_MAX, KIND_BY_ID, KINDS, PROJECT_FILE, PROJECT_LOCK, create_phone, create_project,
                       files_of, is_deck, kind_named, list_projects, name_untitled, prepare_root, project_details,
                       project_dirs, project_path, subdir, update_project)
from .validate import check_request
from .video import (PHONE_LENGTH, PHONE_SHAPE, SOURCE_SUFFIXES, STORYBOARD, check_film, check_storyboard, default_film,
                    film_of, is_video, next_picture, read_storyboard, refuse_markdown, scene_images, scene_named,
                    storyboard_mtime, writes_pictures)

PAGE_DIR = Path(__file__).resolve().parents[1] / "page"
HEARTBEAT_TIMEOUT = 20.0
POLL_INTERVAL = 1.0
KEEPALIVE = 15.0
MAX_BODY = 64 * 1024 * 1024
# Events kept for pages that connect later, and how many: a request's log has an event per turn, subagent, tool
# call start and end, ask, answer and text block, so a long session sends thousands.
HISTORY_KINDS = ("request", "agent", "note", "text", "turn-start", "turn-end", "agent-start", "tool", "tool-end",
                 "ask", "answer", "stopped", "ended")
HISTORY_MAX = 20000
# Seconds a request no `state` has named stays pending (the mod may send a `state` before it reads the request; a
# `state` it could not send while the server counted as down never names one that ran meanwhile).
UNNAMED_GRACE = 30.0
# /api/catalogue until the catalogue is read.
LOADING = {"styles": [], "brands": [], "loading": True}
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
}
# A Range header of one byte range.
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
COPY_CHUNK = 1 << 20


_stdout_lock = threading.Lock()


def stdout_emit(message: dict) -> None:
    """One JSON line to the mod; the lock keeps lines of concurrent handlers whole."""
    line = json.dumps(message) + "\n"
    with _stdout_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def byte_range(header: str | None, size: int) -> tuple[int, int] | None | bool:
    """`(first, last)` byte, inclusive, of a Range header of one byte range within a file of `size` bytes; None
    without such a header (the whole file is sent); False when the range lies outside the file (416)."""
    m = RANGE.match(header.strip()) if header else None
    if not m or not (m.group(1) or m.group(2)):
        return None
    first, last = m.groups()
    if not first:
        suffix = int(last)
        return (max(0, size - suffix), size - 1) if suffix and size else False
    start = int(first)
    if last and int(last) < start:
        return None
    if start >= size:
        return False
    return start, min(int(last), size - 1) if last else size - 1


class Heartbeat:
    """The time of the last heartbeat, counted from creation; expired after `timeout` seconds without one."""

    def __init__(self, timeout: float = HEARTBEAT_TIMEOUT, clock: Callable[[], float] = time.monotonic) -> None:
        self.timeout = timeout
        self.clock = clock
        self.last = clock()

    def beat(self) -> None:
        self.last = self.clock()

    def expired(self) -> bool:
        return self.clock() - self.last > self.timeout


class Studio:
    """State shared by the request handlers and the background loops."""

    def __init__(self, root: str | Path, page_dir: str | Path = PAGE_DIR, emit: Callable[[dict], None] = stdout_emit,
                 heartbeat: Heartbeat | None = None, find_brand: Callable[[], Path | None] | None = None) -> None:
        self.root = prepare_root(Path(root))
        # Finds the brand plugin's folder for load_catalogue (None: the catalogue stays loading).
        self.find_brand = find_brand
        self.page_dir = Path(page_dir).resolve()
        self.emit = emit
        self.heartbeat = heartbeat or Heartbeat()
        self.lock = threading.Lock()
        self.clients: list[queue.Queue] = []
        self.catalogue: dict = LOADING
        # The session's events, the last `state` event and the open `ask` (until `ask-done` or `ended`), sent to
        # each page that connects.
        self.state: dict | None = None
        self.history: collections.deque[dict] = collections.deque(maxlen=HISTORY_MAX)
        self.ask: dict | None = None
        self.samples: frozenset[Path] = frozenset()
        # The requests not yet done, by id, in order: those a `state` named and the last `state` still names, and
        # those no `state` named yet (the mod may read a request after a `state` it sent meanwhile). Kept apart
        # from the bounded history, so a long session cannot drop one.
        self.pending: dict[str, dict] = {}
        self.named: set[str] = set()
        # When each pending request was accepted (time.monotonic()).
        self.accepted: dict[str, float] = {}
        # The last scan of the projects; the first poll takes it and reports nothing.
        self.snapshot: dict[str, dict[str, dict]] | None = None
        self.httpd: ThreadingHTTPServer | None = None
        # Where deleted projects go; None: the user's Trash (trash.trash_dir).
        self.trash_root: Path | None = None

    # Events

    def broadcast(self, event: dict) -> None:
        """Send an event to every page. The session's events (HISTORY_KINDS, the last HISTORY_MAX), the last
        `state` and the open `ask` are kept for pages that connect later; the update and the sending hold one lock,
        so a connecting page gets each event once."""
        with self.lock:
            kind = event.get("kind")
            if kind in HISTORY_KINDS:
                self.history.append(event)
            if kind == "request" and isinstance(event.get("request"), dict):
                self.pending[event["request"].get("id")] = event["request"]
                self.accepted[event["request"].get("id")] = time.monotonic()
            if kind == "state":
                self.state = event
                queued = event.get("queued") if isinstance(event.get("queued"), list) else []
                ids = {i for i in (event.get("current"), *queued) if isinstance(i, str)}
                self.named |= ids
                now = time.monotonic()
                self.pending = {i: r for i, r in self.pending.items() if i in ids
                                or (i not in self.named and now - self.accepted.get(i, now) <= UNNAMED_GRACE)}
                self.accepted = {i: t for i, t in self.accepted.items() if i in self.pending}
            elif kind == "stopped":
                self.pending.pop(event.get("id"), None)
            elif kind == "ask":
                self.ask = event
            elif kind == "ask-done":
                self.ask = None
            elif kind == "ended":
                self.ask = None
                self.pending = {}
                self.named = set()
                if self.state is not None:
                    self.state = {**self.state, "busy": False}
            for client in self.clients:
                client.put(event)

    def connect(self) -> queue.Queue:
        """A new page's queue, holding a `request` event for each request the kept `state` names (current and
        queued) whose own `request` event has left the history, the kept history in order, then the kept `state`
        and `ask`, then `{"kind": "replayed"}`."""
        client: queue.Queue = queue.Queue()
        with self.lock:
            kept = {e["request"].get("id") for e in self.history
                    if e.get("kind") == "request" and isinstance(e.get("request"), dict)}
            state = self.state or {}
            queued = state.get("queued") if isinstance(state.get("queued"), list) else []
            for i in (state.get("current"), *queued):
                if isinstance(i, str) and i not in kept and i in self.pending:
                    client.put({"kind": "request", "request": self.pending[i]})
            for event in (*self.history, self.state, self.ask):
                if event is not None:
                    client.put(event)
            client.put({"kind": "replayed"})
            self.clients.append(client)
            return client

    def is_pending(self, request_id: str) -> bool:
        with self.lock:
            return request_id in self.pending

    def pending_requests(self) -> list[dict]:
        """The current and queued requests."""
        with self.lock:
            return list(self.pending.values())

    def scan(self) -> dict[str, dict[str, dict]]:
        """`{kind id: {project dir: {file: (mtime_ns, size)}}}` of every project."""
        return {k.id: {str(p): files_of(p) for p in project_dirs(self.root, k)} for k in KINDS}

    def poll(self) -> list[dict]:
        """Compare the projects with the last scan and broadcast `projects` and `changed`; return the events."""
        current = self.scan()
        if self.snapshot is None:
            self.snapshot = current
            return []
        events = []
        # `kind` names the event, so the kind of project is `project_kind`.
        for kind in KIND_BY_ID:
            before, now = self.snapshot.get(kind, {}), current[kind]
            if set(before) != set(now):
                events.append({"kind": "projects", "project_kind": kind})
            for d in sorted(set(before) & set(now)):
                if before[d] != now[d]:
                    events.append({"kind": "changed", "project_kind": kind, "project": d})
        self.snapshot = current
        for e in events:
            self.broadcast(e)
        return events

    # Catalogue

    def load_catalogue(self) -> None:
        """Read the catalogue from the brand plugin found by find_brand, allow its samples in /file and broadcast
        `{"kind": "catalogue"}`. An unexpected failure is logged and answered as an error."""
        try:
            catalogue, samples = read_catalogue(self.find_brand() if self.find_brand else None)
        except Exception as e:  # noqa: BLE001 - the page gets an answer instead of loading forever
            log(f"studio server: cannot load the catalogue: {type(e).__name__}: {e}")
            catalogue, samples = {"styles": [], "brands": [], "error": f"{type(e).__name__}: {e}"}, frozenset()
        if "error" in catalogue:
            log(f"studio server: {catalogue['error']}")
        with self.lock:
            self.catalogue, self.samples = catalogue, samples
        self.broadcast({"kind": "catalogue"})

    def start_catalogue(self) -> threading.Thread:
        """load_catalogue in a daemon thread, so `ready` does not wait on `claude plugin list`."""
        t = threading.Thread(target=self.load_catalogue, daemon=True)
        t.start()
        return t

    # Server

    def serve(self, port: int = 0) -> ThreadingHTTPServer:
        """An HTTP server on 127.0.0.1 (`port` 0: a free one); the caller runs serve_forever."""
        handler = type("StudioHandler", (Handler,), {"studio": self})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        return self.httpd

    @property
    def port(self) -> int:
        assert self.httpd is not None
        return self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Handler(BaseHTTPRequestHandler):
    studio: Studio

    def log_message(self, format, *args):
        log(format % args)

    # Helpers

    def reply(self, status: int, body: bytes = b"", kind: str = "text/plain; charset=utf-8",
              headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-cache")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def reply_json(self, status: int, value: object) -> None:
        self.reply(status, json.dumps(value).encode(), "application/json")

    def read_json(self) -> object:
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            raise HttpError(400, "bad content-length") from None
        if length > MAX_BODY:
            raise HttpError(413, "request body too large")
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise HttpError(400, "the body is not JSON") from None

    def own_host(self) -> bool:
        port = self.studio.port
        return self.headers.get("host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def own_origin(self) -> bool:
        origin = self.headers.get("origin")
        port = self.studio.port
        return origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def dispatch(self, routes: dict[str, Callable[[dict], None]]) -> None:
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if not self.own_host():
                raise HttpError(403, "unknown host")
            if self.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
                raise HttpError(403, "cross-site request")
            if self.command == "POST" and not self.own_origin():
                raise HttpError(403, "cross-origin request")
            if self.command == "GET" and url.path.startswith("/static/"):
                return self.static(url.path[len("/static/"):])
            route = routes.get(url.path)
            if route is None:
                raise HttpError(404, f"no {url.path}")
            route(query)
        except HttpError as e:
            self.reply_json(e.status, {"error": e.message, **e.extra})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001 - answer instead of dropping the connection
            log(f"studio server: {self.command} {url.path}: {type(e).__name__}: {e}")
            self.reply_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self.dispatch({
            "/": lambda q: self.static("index.html"),
            "/api/config": self.get_config,
            "/api/projects": self.get_projects,
            "/api/project": lambda q: self.reply_json(200, project_details(self.studio.root, q.get("dir"))),
            "/api/catalogue": lambda q: self.reply_json(200, self.studio.catalogue),
            "/api/models": lambda q: self.reply_json(200, read_models()),
            "/file": self.get_file,
            "/events": self.events,
        })

    def do_POST(self):
        self.dispatch({
            "/api/request": self.post_request,
            "/api/stop": self.post_stop,
            "/api/marked": self.post_marked,
            "/api/refs": self.post_refs,
            "/api/new": self.post_new,
            "/api/autonomy": self.post_autonomy,
            "/api/name": self.post_name,
            "/api/delete": self.post_delete,
            "/api/chosen": self.post_chosen,
            "/api/assembly": self.post_assembly,
            "/api/sources": self.post_sources,
            "/api/storyboard": self.post_storyboard,
            "/api/film": self.post_film,
            "/api/scene-style": self.post_scene_style,
            "/api/picture": self.post_picture,
            "/event": self.post_event,
            "/heartbeat": self.post_heartbeat,
        })

    # GET

    def static(self, rel: str) -> None:
        page = self.studio.page_dir
        target = (page / unquote(rel)).resolve()
        if not inside(target, page) or target == page:
            raise HttpError(403, "outside the page directory")
        if not target.is_file():
            raise HttpError(404, f"no page file {rel}")
        self.reply(200, target.read_bytes(), content_type(target))

    def get_config(self, q: dict) -> None:
        self.reply_json(200, {
            "root": str(self.studio.root),
            "kinds": [k._asdict() for k in KINDS],
            "film": default_film(),
        })

    def get_projects(self, q: dict) -> None:
        self.reply_json(200, list_projects(self.studio.root, kind_named(q.get("kind"))))

    def get_file(self, q: dict) -> None:
        p = resolve_abs(q.get("path"), "path")
        if not inside(p, self.studio.root) and p not in self.studio.samples:
            raise HttpError(403, "not a file of the projects root or the catalogue")
        if not p.is_file():
            raise HttpError(404, f"no file {p}")
        headers = {"x-content-type-options": "nosniff", "content-security-policy": "sandbox", "accept-ranges": "bytes"}
        if q.get("download") == "1":
            headers["content-disposition"] = f'attachment; filename="{safe_name(p.name, "file")}"'
        size = p.stat().st_size
        rng = byte_range(self.headers.get("range"), size)
        if rng is False:
            return self.reply(416, b"", content_type(p), {**headers, "content-range": f"bytes */{size}"})
        if rng is None:
            return self.send_file(200, p, 0, size, headers)
        first, last = rng
        self.send_file(206, p, first, last - first + 1, {**headers, "content-range": f"bytes {first}-{last}/{size}"})

    def send_file(self, status: int, path: Path, start: int, length: int, headers: dict[str, str]) -> None:
        """`length` bytes of `path` from `start`, read in chunks."""
        with path.open("rb") as f:
            self.send_response(status)
            self.send_header("content-type", content_type(path))
            self.send_header("content-length", str(length))
            self.send_header("cache-control", "no-cache")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            f.seek(start)
            while length > 0:
                chunk = f.read(min(COPY_CHUNK, length))
                if not chunk:
                    break
                self.wfile.write(chunk)
                length -= len(chunk)

    def events(self, q: dict) -> None:
        studio = self.studio
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        self.close_connection = True
        client = studio.connect()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = client.get(timeout=KEEPALIVE)
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with studio.lock:
                studio.clients.remove(client)

    # POST

    def post_request(self, q: dict) -> None:
        req = check_request(self.read_json(), self.studio.root)
        req["id"] = uuid.uuid4().hex[:12]
        req["time"] = datetime.now().astimezone().isoformat(timespec="seconds")
        # The model of each task when the request is accepted, so the agent records the model, not only the tier.
        req["models"] = read_models()["tasks"]
        created = None
        action = req["action"]
        if action in ("generate", "storyboard") and req["project"] is None:
            created = create_project(self.studio.root, KIND_BY_ID[req["kind"]], req["brief"], req["time"],
                                     req["autonomy"], film=req.get("film") if action == "storyboard" else None)
            req["project"] = str(created)
        elif action in ("generate", "storyboard"):
            name_untitled(Path(req["project"]), req["brief"])
            if action == "storyboard":
                update_project(Path(req["project"]), lambda meta: meta.update(film=req["film"]))
        elif action == "phone":
            created = create_phone(Path(req["project"]), req["version"], req["time"], PHONE_SHAPE, PHONE_LENGTH)
            req["target"] = str(created)
        try:
            self.studio.emit({"type": "request", "request": req})
        except (OSError, ValueError) as e:
            log(f"studio server: cannot write the request to stdout: {e}")
            if created is not None:  # no agent will fill it, so the page does not list an empty project
                shutil.rmtree(created, ignore_errors=True)
            raise HttpError(503, "the request could not be passed to Claude Code") from None
        self.studio.broadcast({"kind": "request", "request": req})
        answer = {"id": req["id"], "project": req["project"]}
        if "target" in req:
            answer["target"] = req["target"]
        self.reply_json(202, answer)

    def post_stop(self, q: dict) -> None:
        """Passes the user's Stop of a current or queued request to the mod; 409 for a request that is neither."""
        body = self.read_json()
        request_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(request_id, str) or not request_id:
            raise HttpError(400, "id must be a request id")
        if not self.studio.is_pending(request_id):
            raise HttpError(409, "the request is neither running nor waiting")
        try:
            self.studio.emit({"type": "stop", "id": request_id})
        except (OSError, ValueError) as e:
            log(f"studio server: cannot write the stop to stdout: {e}")
            raise HttpError(503, "the stop could not be passed to Claude Code") from None
        self.reply_json(202, {"id": request_id})

    def _body_project(self, *, markdown: bool = False) -> tuple[dict, Path]:
        """The body and its project; a short-video project holding storyboard.md takes no write, unless `markdown`
        (a write of project.json only, or a move of the whole project)."""
        body = self.read_json()
        if not isinstance(body, dict):
            raise HttpError(400, "the body must be a JSON object")
        project = project_path(self.studio.root, body.get("project"))
        if is_video(project) and not markdown:
            refuse_markdown(project)
        return body, project

    def _body_video(self) -> tuple[dict, Path]:
        body, project = self._body_project()
        if not is_video(project):
            raise HttpError(400, "project is not a short-video project")
        return body, project

    def _body_deck(self) -> tuple[dict, Path]:
        body, project = self._body_project()
        if not is_deck(project):
            raise HttpError(400, "project is not a slide deck")
        return body, project

    def _images_dir(self, body: dict, project: Path) -> Path:
        """The directory holding the versions a body names: the project, for a deck the directory of its existing
        slide `slide`, for a short-video project `images/<scene>/` of its scene `scene`."""
        if is_video(project):
            if body.get("slide") is not None:
                raise HttpError(400, "slide is only for slide decks")
            return scene_images(project, body)
        if body.get("scene") is not None:
            raise HttpError(400, "scene is only for short-video projects")
        if not is_deck(project):
            if body.get("slide") is not None:
                raise HttpError(400, "slide is only for slide decks")
            return project
        return slide_images(project, body)

    def post_marked(self, q: dict) -> None:
        body, project = self._body_project()
        project = self._images_dir(body, project)
        n = positive(body, "version")
        image = project / f"v{n}.png"
        if not image.is_file():
            raise HttpError(400, f"version {n} has no image in {project}")
        _, data = decode_data_url(body.get("png"), ("image/png",))
        mask = None
        if body.get("mask") is not None:
            _, mask = decode_data_url(body["mask"], ("image/png",))
            size = png_size(mask)
            if size is None:
                raise HttpError(400, "the mask is not a PNG")
            with image.open("rb") as f:
                image_size = png_size(f.read(24))
            if size != image_size:
                raise HttpError(400, f"the mask is {size[0]}x{size[1]} pixels, not the size of {image.name}"
                                     + (f" ({image_size[0]}x{image_size[1]})" if image_size else ""))
        marks = subdir(project, "marks")
        target = write_new(marks, f"v{n}-marked.png", data, numbered=True)
        if mask is None:
            return self.reply_json(200, {"path": str(target)})
        # The mask takes the k of the marked copy; a mask left with that k by a deleted marked copy is replaced.
        k = target.stem.rsplit("-", 1)[1]
        mask_path = marks / f"v{n}-mask-{k}.png"
        write_atomic(mask_path, mask)
        self.reply_json(200, {"path": str(target), "mask": str(mask_path)})

    def post_refs(self, q: dict) -> None:
        body, project = self._body_project()
        name = body.get("name")
        if not isinstance(name, str):
            raise HttpError(400, "name must be a string")
        mime, data = decode_data_url(body.get("data"), tuple(IMAGE_SUFFIXES))
        fname = safe_name(name)
        stem, suffix = os.path.splitext(fname)
        if suffix.lower() not in IMAGE_SUFFIXES[mime]:
            known = any(suffix.lower() in s for s in IMAGE_SUFFIXES.values())
            fname = (stem if known else fname) + IMAGE_SUFFIXES[mime][0]
        target = write_new(subdir(project, "refs"), fname, data)
        self.reply_json(200, {"path": str(target)})

    def post_new(self, q: dict) -> None:
        """An untitled project of `kind` (with `autonomy`), made when a reference image is added to a blank
        workspace; its first `generate` names it from the brief."""
        body = self.read_json()
        if not isinstance(body, dict):
            raise HttpError(400, "the body must be a JSON object")
        kind = kind_named(body.get("kind"))
        autonomy = body.get("autonomy", AUTONOMY[0])
        if autonomy not in AUTONOMY:
            raise HttpError(400, f"autonomy must be one of {', '.join(AUTONOMY)}")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        project = create_project(self.studio.root, kind, "", now, autonomy)
        self.reply_json(200, {"project": str(project)})

    def post_autonomy(self, q: dict) -> None:
        body, project = self._body_project(markdown=True)
        autonomy = body.get("autonomy")
        if autonomy not in AUTONOMY:
            raise HttpError(400, f"autonomy must be one of {', '.join(AUTONOMY)}")
        update_project(project, lambda meta: meta.update(autonomy=autonomy))
        self.reply_json(200, {"autonomy": autonomy})

    def post_name(self, q: dict) -> None:
        """The user's name of a project: `name` in project.json, and `named` true so the agent keeps it."""
        body, project = self._body_project(markdown=True)
        name = body.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > NAME_MAX:
            raise HttpError(400, f"name must be a non-blank string of at most {NAME_MAX} characters")
        name = " ".join(name.split())
        update_project(project, lambda meta: meta.update(name=name, named=True))
        self.reply_json(200, {"name": name})

    def post_delete(self, q: dict) -> None:
        """Moves a project to the user's Trash; 409 while a current or queued request works on it."""
        body, project = self._body_project(markdown=True)
        busy = [r for r in self.studio.pending_requests()
                if str(project) in (r.get("project"), r.get("target"))]
        if busy:
            raise HttpError(409, "Claude is working on this project; delete it once the request is done")
        meta = read_json(project / PROJECT_FILE)
        name = meta.get("name") if isinstance(meta, dict) and isinstance(meta.get("name"), str) else project.name
        label = f"Studio {project.parent.name} - {slug(name) or project.name} ({project.name})"
        try:
            moved = move_to_trash(project, label, self.studio.trash_root)
        except OSError as e:
            raise HttpError(500, f"could not move the project to the Trash: {e}")
        self.reply_json(200, {"trash": str(moved)})

    def post_chosen(self, q: dict) -> None:
        """Sets the chosen version of a deck's slide in `chosen` of project.json."""
        body, deck = self._body_deck()
        d = self._images_dir(body, deck)
        k, n = body["slide"], positive(body, "version")
        if n not in [v["n"] for v in versions_of(d)]:
            raise HttpError(400, f"version {n} is not a version of slide {k}")

        def choose(meta: dict) -> None:
            chosen = meta.get("chosen") if isinstance(meta.get("chosen"), dict) else {}
            meta["chosen"] = {**chosen, str(k): n}
        meta = update_project(deck, choose)
        self.reply_json(200, {"chosen": meta["chosen"]})

    def post_assembly(self, q: dict) -> None:
        """Sets `assembly` of a deck's project.json."""
        body, deck = self._body_deck()
        assembly = body.get("assembly")
        if assembly not in ASSEMBLY:
            raise HttpError(400, f"assembly must be one of {', '.join(ASSEMBLY)}")
        update_project(deck, lambda meta: meta.update(assembly=assembly))
        self.reply_json(200, {"assembly": assembly})

    def post_sources(self, q: dict) -> None:
        """Writes a source or own music track to `sources/` of a short-video project."""
        body, project = self._body_video()
        name = body.get("name")
        if not isinstance(name, str):
            raise HttpError(400, "name must be a string")
        fname = safe_name(name, "source")
        if os.path.splitext(fname)[1].lower() not in SOURCE_SUFFIXES:
            raise HttpError(400, f"a source must have one of the suffixes {', '.join(SOURCE_SUFFIXES)}")
        _, data = decode_data_url(body.get("data"), None)
        target = write_new(subdir(project, "sources"), fname, data)
        self.reply_json(200, {"path": str(target)})

    def post_storyboard(self, q: dict) -> None:
        """Replaces storyboard.json with the page's whole structure, when `base` is the current storyboard_mtime."""
        body, project = self._body_video()
        base = body.get("base")
        if base is not None and not isinstance(base, str):
            raise HttpError(400, "base must be the storyboard_mtime string or null")
        storyboard = body.get("storyboard")
        with PROJECT_LOCK:
            current = storyboard_mtime(project)
            if base != current:
                raise HttpError(409, "the storyboard changed meanwhile",
                                {"storyboard": read_storyboard(project), "storyboard_mtime": current})
            problems = check_storyboard(storyboard)
            if problems:
                raise HttpError(400, "; ".join(problems))
            write_atomic(project / STORYBOARD, (json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n").encode())
            mtime = storyboard_mtime(project)
        self.reply_json(200, {"storyboard_mtime": mtime})

    def post_film(self, q: dict) -> None:
        """Replaces the given keys of `film` in project.json."""
        body, project = self._body_video()

        def change(meta: dict) -> None:
            meta["film"] = check_film(project, film_of(meta), body.get("film"), whole=False)
        self.reply_json(200, {"film": update_project(project, change)["film"]})

    def post_scene_style(self, q: dict) -> None:
        """Sets or removes a scene's own style in `scene_styles` of project.json."""
        body, project = self._body_video()
        scene = scene_named(project, body)
        style = body.get("style")
        if style is not None and not (isinstance(style, str) and style.strip()):
            raise HttpError(400, "style must be a style name or null")

        def change(meta: dict) -> None:
            styles = dict(meta["scene_styles"]) if isinstance(meta.get("scene_styles"), dict) else {}
            if style is None:
                styles.pop(scene, None)
            else:
                styles[scene] = style
            meta["scene_styles"] = styles
        self.reply_json(200, {"scene_styles": update_project(project, change)["scene_styles"]})

    def post_picture(self, q: dict) -> None:
        """Writes the user's own picture as the next picture version of a scene, with its sidecar."""
        body, project = self._body_video()
        scene = scene_named(project, body)
        name = body.get("name")
        if not isinstance(name, str):
            raise HttpError(400, "name must be a string")
        _, data = decode_data_url(body.get("data"), ("image/png",))
        if png_size(data) is None:
            raise HttpError(400, "the picture is not a PNG")
        if any(writes_pictures(r, str(project), scene) for r in self.studio.pending_requests()):
            raise HttpError(409, f"a request is making pictures of scene {scene}")
        if (project / "images").is_symlink() or (project / "images" / scene).is_symlink():
            raise HttpError(400, f"{project / 'images' / scene} is not a directory of the project")
        with PROJECT_LOCK:
            meta = read_json(project / PROJECT_FILE)
            d = subdir(subdir(project, "images"), scene)
            n = next_picture(d)
            while True:
                try:
                    fd = os.open(d / f"v{n}.png", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                    break
                except FileExistsError:
                    n += 1
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            sidecar = {"action": "own-picture", "original": name,
                       "created": datetime.now().astimezone().isoformat(timespec="seconds"), "kind": "short-video",
                       "shape": film_of(meta)["shape"], "prompt": None, "scene": None, "style": None, "brand": None,
                       "model": None, "model_id": None, "change": None, "source": None, "refs": []}
            write_atomic(d / f"v{n}.json", (json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n").encode())
        self.reply_json(200, {"version": n, "path": str(d / f"v{n}.png")})

    def post_event(self, q: dict) -> None:
        body = self.read_json()
        if not isinstance(body, dict) or not isinstance(body.get("kind"), str):
            raise HttpError(400, "an event is a JSON object with a kind")
        self.studio.broadcast(body)
        self.reply(204)

    def post_heartbeat(self, q: dict) -> None:
        self.read_json()
        self.studio.heartbeat.beat()
        self.reply(204)


# Background loops

def parent_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(parent_pid: int | None, exit_fn: Callable[[int], None], interval: float = 1.0) -> None:
    """Exit when this process's parent id changes or `parent_pid` (the process that started the wrapper; uv run
    sits between it and Python) is gone. macOS and Linux only."""
    first = os.getppid()
    while True:
        if os.getppid() != first or (parent_pid and not parent_alive(parent_pid)):
            log("studio server: parent process ended")
            exit_fn(0)
            return
        time.sleep(interval)


def watch_heartbeat(heartbeat: Heartbeat, exit_fn: Callable[[int], None], interval: float = 1.0) -> None:
    while True:
        if heartbeat.expired():
            log(f"studio server: no heartbeat for {heartbeat.timeout:g} s")
            exit_fn(0)
            return
        time.sleep(interval)


def watch_projects(studio: Studio, interval: float = POLL_INTERVAL, stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    while True:
        try:
            studio.poll()
        except OSError as e:
            log(f"studio server: scan failed: {e}")
        if stop.wait(interval):
            return


def start_loops(studio: Studio, parent_pid: int | None = None, exit_fn: Callable[[int], None] = os._exit) -> None:
    loops = [(watch_projects, (studio,)), (watch_heartbeat, (studio.heartbeat, exit_fn))]
    if sys.platform != "win32":
        loops.append((watch_parent, (parent_pid, exit_fn)))
    for target, args in loops:
        threading.Thread(target=target, args=args, daemon=True).start()
