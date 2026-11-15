"""HTTP handler of the editor server: the page, the animation folder under `/anim/`, the API and the events."""

from __future__ import annotations

import json
import mimetypes
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .editor import Editor
from .http_error import HttpError
from .log import log

BODY_MAX = 1_000_000
KEEPALIVE = 15.0
COPY_CHUNK = 1 << 16
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html",
         ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2"}


def content_type(path: Path) -> str:
    known = TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"{known}; charset=utf-8" if known.startswith("text/") or known == "application/json" else known


class Handler(BaseHTTPRequestHandler):
    editor: Editor
    server_version = "html-animation-server"

    def log_message(self, format: str, *args) -> None:  # noqa: A002 (the base class's name)
        log("html-animation server: " + format % args)

    # Replies

    def reply(self, status: int, body: bytes = b"", ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def reply_json(self, status: int, value: object) -> None:
        self.reply(status, json.dumps(value).encode())

    def send_file(self, path: Path) -> None:
        if not path.is_file():
            raise HttpError(404, "not found")
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("content-type", content_type(path))
        self.send_header("content-length", str(size))
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as f:
            while chunk := f.read(COPY_CHUNK):
                self.wfile.write(chunk)

    def read_json(self) -> object:
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            raise HttpError(400, "bad content-length") from None
        if length > BODY_MAX:
            raise HttpError(413, "body too large")
        try:
            return json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            raise HttpError(400, "the body is not JSON") from None

    def own_hosts(self) -> tuple[str, str]:
        port = self.server.server_address[1]
        return f"127.0.0.1:{port}", f"localhost:{port}"

    def check_request(self) -> None:
        """Checks every request before it is routed, as the Studio server does.

        - The Host header must be 127.0.0.1 or localhost on this server's port: a page on another name that
          resolves to 127.0.0.1 (DNS rebinding) is refused.
        - `sec-fetch-site` must be `same-origin` or `none` (absent counts as same-origin), except for a GET of the
          animation's own files: the sandboxed iframe has an opaque origin, so its scripts load as `cross-site`.
        - A POST with an Origin header must come from this server's own origin; the sandboxed animation (origin
          `null`) and other sites are refused. The mod sends no Origin."""
        if self.headers.get("host", "") not in self.own_hosts():
            raise HttpError(403, "unknown host")
        is_anim = self.command in ("GET", "HEAD") and urlsplit(self.path).path.startswith("/anim/")
        if not is_anim and self.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            raise HttpError(403, "cross-site request")
        origin = self.headers.get("origin")
        if self.command == "POST" and origin is not None and origin not in {f"http://{h}" for h in self.own_hosts()}:
            raise HttpError(403, "cross-origin request refused")

    def guarded(self, action) -> None:
        try:
            self.check_request()
            action()
        except HttpError as e:
            self.reply_json(e.status, {"error": e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass

    # GET

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self.guarded(self.get)

    def get(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self.send_file(self.editor.page_dir / "index.html")
        elif path.startswith("/page/"):
            name = path.removeprefix("/page/")
            if not name or "/" in name or "\\" in name or name.startswith(".") or "%" in name:
                raise HttpError(403, "path refused")
            self.send_file(self.editor.page_dir / name)
        elif path.startswith("/anim/"):
            self.send_file(self.editor.folder.resolve(path.removeprefix("/anim/")))
        elif path == "/api/state":
            self.reply_json(200, self.editor.state())
        elif path == "/api/events":
            self.events()
        else:
            raise HttpError(404, "not found")

    def events(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        self.close_connection = True
        client = self.editor.connect()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = client.get(timeout=KEEPALIVE)
                    kind = event.pop("kind")
                    self.wfile.write(f"event: {kind}\ndata: {json.dumps(event)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.editor.disconnect(client)

    # POST

    def do_POST(self) -> None:
        self.guarded(self.post)

    def post(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/comment":
            self.reply_json(200, self.editor.view(self.editor.add_comment(self.read_json())))
        elif path == "/api/stop":
            body = self.read_json()
            given = body.get("id") if isinstance(body, dict) else None
            self.editor.stop(given if isinstance(given, str) else None)
            self.reply_json(200, {"ok": True})
        elif path == "/api/agent":
            self.editor.agent_message(self.read_json())
            self.reply_json(200, {"ok": True})
        else:
            raise HttpError(404, "not found")


def serve(editor: Editor, port: int = 0) -> ThreadingHTTPServer:
    """A server on 127.0.0.1 (`port` 0: any free port) bound to `editor`; `editor.url` is set."""
    handler = type("BoundHandler", (Handler,), {"editor": editor})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    editor.httpd = httpd
    editor.url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    return httpd
