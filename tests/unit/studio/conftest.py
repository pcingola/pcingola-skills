"""A studio server on a temporary projects root and page directory, served in a thread."""
from __future__ import annotations

import base64
import http.client
import json
import struct
import threading
import zlib
from pathlib import Path

import pytest

from studio_server.server import Heartbeat, Studio

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def png(width: int, height: int, alpha: bool = False) -> bytes:
    """A black PNG of `width` x `height` pixels, RGB or RGBA (alpha 255)."""
    channels = 4 if alpha else 3
    row = b"\0" + (b"\0\0\0\xff" if alpha else b"\0\0\0") * width
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6 if channels == 4 else 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def data_url(data: bytes = PNG, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


class Client:
    """HTTP calls to the server, with the Host header of the server unless a test sets another."""

    def __init__(self, studio: Studio) -> None:
        self.studio = studio
        self.port = studio.port

    def call(self, method: str, path: str, body: object = None, headers: dict | None = None,
             raw: bytes | None = None) -> tuple[int, dict, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"content-type": "application/json"} if data is not None else {}
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        out = r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        conn.close()
        return out

    def get(self, path: str, **kw) -> tuple[int, object]:
        status, _, body = self.call("GET", path, **kw)
        return status, json.loads(body) if body else None

    def post(self, path: str, body: object = None, **kw) -> tuple[int, object]:
        status, _, data = self.call("POST", path, body, **kw)
        return status, json.loads(data) if data else None


class Events:
    """A connection to /events; `next()` returns the next event. The replay's end marker `{"kind": "replayed"}` is
    read into `replayed` and skipped, so tests compare the events around it."""

    def __init__(self, port: int) -> None:
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.conn.request("GET", "/events")
        self.resp = self.conn.getresponse()
        assert self.resp.status == 200
        assert self.resp.getheader("content-type") == "text/event-stream"
        assert self.resp.fp.readline() == b": connected\n"
        self.replayed = False

    def next(self) -> dict:
        while True:
            line = self.resp.fp.readline()
            assert line, "the event stream ended"
            if line.startswith(b"data: "):
                event = json.loads(line[6:])
                if event == {"kind": "replayed"} and not self.replayed:
                    self.replayed = True
                    continue
                return event

    def close(self) -> None:
        self.conn.close()


@pytest.fixture
def emitted() -> list[dict]:
    return []


@pytest.fixture
def page(tmp_path: Path) -> Path:
    d = tmp_path / "page"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>Studio</title>", encoding="utf-8")
    (d / "studio.css").write_text("body {}", encoding="utf-8")
    (d / "shell.js").write_text("export {}", encoding="utf-8")
    return d


@pytest.fixture
def studio(tmp_path: Path, page: Path, emitted: list):
    s = Studio(tmp_path / "Studio", page_dir=page, emit=emitted.append, heartbeat=Heartbeat(20.0))
    httpd = s.serve()
    t = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    t.start()
    yield s
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def client(studio: Studio) -> Client:
    return Client(studio)


@pytest.fixture
def events(studio: Studio):
    opened = []

    def connect() -> Events:
        e = Events(studio.port)
        opened.append(e)
        return e

    yield connect
    for e in opened:
        e.close()


def make_project(root: Path, name: str = "cat", versions: tuple[int, ...] = (1,), directory: str = "images") -> Path:
    """A project `<root>/<directory>/<name>` with project.json and versions `versions` (v<N>.png and v<N>.json)."""
    p = root / directory / name
    p.mkdir(parents=True)
    (p / "project.json").write_text(json.dumps(
        {"name": name.title(), "brief": f"a {name}", "created": "2026-11-07T10:00:00+00:00", "autonomy": "step",
         "settings": {}}), encoding="utf-8")
    for n in versions:
        (p / f"v{n}.png").write_bytes(PNG)
        (p / f"v{n}.json").write_text(json.dumps({"prompt": f"prompt {n}", "style": "ink", "source": None}),
                                      encoding="utf-8")
    return p
