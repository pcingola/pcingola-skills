"""The studio HTTP server: page, project files, requests to the mod, events to the page.

stdout carries one JSON object per line to the mod (`ready`, `request`); stderr is a log.
Requests are accepted only with a `Host` of this server, and POSTs only without an `Origin` (the mod) or with this
server's own origin (the page), so another web page in the browser can neither read project files through a
rebound host name nor send requests.
"""

from __future__ import annotations

import collections
import json
import os
import queue
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
from .paths import (IMAGE_SUFFIXES, HttpError, decode_data_url, inside, log, png_size, positive, resolve_abs,
                    safe_name, write_atomic, write_new)
from .projects import (AUTONOMY, KIND_BY_ID, KINDS, create_project, files_of, is_deck, kind_named, list_projects,
                       name_untitled, prepare_root, project_details, project_dirs, project_path, subdir,
                       update_project)
from .validate import check_request

PAGE_DIR = Path(__file__).resolve().parents[1] / "page"
HEARTBEAT_TIMEOUT = 20.0
POLL_INTERVAL = 1.0
KEEPALIVE = 15.0
MAX_BODY = 64 * 1024 * 1024
# Events kept for pages that connect later, and how many.
HISTORY_KINDS = ("request", "agent", "note", "turn", "ended")
HISTORY_MAX = 1000
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
}


_stdout_lock = threading.Lock()


def stdout_emit(message: dict) -> None:
    """One JSON line to the mod; the lock keeps lines of concurrent handlers whole."""
    line = json.dumps(message) + "\n"
    with _stdout_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


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
        # The last scan of the projects; the first poll takes it and reports nothing.
        self.snapshot: dict[str, dict[str, dict]] | None = None
        self.httpd: ThreadingHTTPServer | None = None

    # Events

    def broadcast(self, event: dict) -> None:
        """Send an event to every page. The session's events (HISTORY_KINDS, the last HISTORY_MAX), the last
        `state` and the open `ask` are kept for pages that connect later; the update and the sending hold one lock,
        so a connecting page gets each event once."""
        with self.lock:
            kind = event.get("kind")
            if kind in HISTORY_KINDS:
                self.history.append(event)
            if kind == "state":
                self.state = event
            elif kind == "ask":
                self.ask = event
            elif kind == "ask-done":
                self.ask = None
            elif kind == "ended":
                self.ask = None
                if self.state is not None:
                    self.state = {**self.state, "busy": False}
            for client in self.clients:
                client.put(event)

    def connect(self) -> queue.Queue:
        """A new page's queue, holding the kept history in order, then the kept `state` and `ask`, then
        `{"kind": "replayed"}`."""
        client: queue.Queue = queue.Queue()
        with self.lock:
            for event in (*self.history, self.state, self.ask):
                if event is not None:
                    client.put(event)
            client.put({"kind": "replayed"})
            self.clients.append(client)
            return client

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
            self.reply_json(e.status, {"error": e.message})
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
            "/file": self.get_file,
            "/events": self.events,
        })

    def do_POST(self):
        self.dispatch({
            "/api/request": self.post_request,
            "/api/marked": self.post_marked,
            "/api/refs": self.post_refs,
            "/api/new": self.post_new,
            "/api/autonomy": self.post_autonomy,
            "/api/chosen": self.post_chosen,
            "/api/assembly": self.post_assembly,
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
        })

    def get_projects(self, q: dict) -> None:
        self.reply_json(200, list_projects(self.studio.root, kind_named(q.get("kind"))))

    def get_file(self, q: dict) -> None:
        p = resolve_abs(q.get("path"), "path")
        if not inside(p, self.studio.root) and p not in self.studio.samples:
            raise HttpError(403, "not a file of the projects root or the catalogue")
        if not p.is_file():
            raise HttpError(404, f"no file {p}")
        headers = {"x-content-type-options": "nosniff", "content-security-policy": "sandbox"}
        if q.get("download") == "1":
            headers["content-disposition"] = f'attachment; filename="{safe_name(p.name, "file")}"'
        self.reply(200, p.read_bytes(), content_type(p), headers)

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
        created = None
        if req["action"] == "generate" and req["project"] is None:
            created = create_project(self.studio.root, KIND_BY_ID[req["kind"]], req["brief"], req["time"],
                                     req["autonomy"])
            req["project"] = str(created)
        elif req["action"] == "generate":
            name_untitled(Path(req["project"]), req["brief"])
        try:
            self.studio.emit({"type": "request", "request": req})
        except (OSError, ValueError) as e:
            log(f"studio server: cannot write the request to stdout: {e}")
            if created is not None:  # no agent will fill it, so the page does not list an empty project
                shutil.rmtree(created, ignore_errors=True)
            raise HttpError(503, "the request could not be passed to Claude Code") from None
        self.studio.broadcast({"kind": "request", "request": req})
        self.reply_json(202, {"id": req["id"], "project": req["project"]})

    def _body_project(self) -> tuple[dict, Path]:
        body = self.read_json()
        if not isinstance(body, dict):
            raise HttpError(400, "the body must be a JSON object")
        return body, project_path(self.studio.root, body.get("project"))

    def _body_deck(self) -> tuple[dict, Path]:
        body, project = self._body_project()
        if not is_deck(project):
            raise HttpError(400, "project is not a slide deck")
        return body, project

    def _images_dir(self, body: dict, project: Path) -> Path:
        """The directory holding the versions a body names: the project, or for a deck the directory of its
        existing slide `slide`."""
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
        body, project = self._body_project()
        autonomy = body.get("autonomy")
        if autonomy not in AUTONOMY:
            raise HttpError(400, f"autonomy must be one of {', '.join(AUTONOMY)}")
        update_project(project, lambda meta: meta.update(autonomy=autonomy))
        self.reply_json(200, {"autonomy": autonomy})

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
