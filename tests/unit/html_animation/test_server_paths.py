"""Unit tests of the editor server's path checks: `AnimationFolder.resolve` and `GET /anim/` through a real server."""
from __future__ import annotations

import http.client
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from html_animation_server.editor import Editor
from html_animation_server.folder import AnimationFolder
from html_animation_server.handler import serve
from html_animation_server.http_error import HttpError


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """`anim/` with index.html, chapters/intro.js and a link to a file inside; `secret.txt` beside `anim/`, with a
    file link and a directory link to it from inside."""
    anim = tmp_path / "anim"
    (anim / "chapters").mkdir(parents=True)
    (anim / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (anim / "chapters" / "intro.js").write_text("// intro", encoding="utf-8")
    (anim / "name with space.txt").write_text("spaced", encoding="utf-8")
    (anim / "%2e%2e").write_text("literal", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    os.symlink(tmp_path / "secret.txt", anim / "leak.txt")
    os.symlink(tmp_path, anim / "up")
    os.symlink(anim / "index.html", anim / "same.html")
    return anim


INSIDE = {
    "index.html": "index.html",
    "chapters/intro.js": "chapters/intro.js",
    "chapters/./intro.js": "chapters/intro.js",
    "name%20with%20space.txt": "name with space.txt",
    "same.html": "index.html",
    # Decoded once: `%252e%252e` is the file named `%2e%2e`, not a parent step.
    "%252e%252e": "%2e%2e",
}

OUTSIDE = [
    "../secret.txt",
    "chapters/../../secret.txt",
    "%2e%2e/secret.txt",
    "%2E%2E%2Fsecret.txt",
    "..%2fsecret.txt",
    "..%5csecret.txt",
    "..\\secret.txt",
    "/etc/passwd",
    "%2Fetc%2Fpasswd",
    "C:/Windows/win.ini",
    "leak.txt",
    "up/secret.txt",
    "index.html%00.png",
    "%ff%fe",
    "",
]


@pytest.mark.parametrize(("url_path", "relative"), INSIDE.items())
def test_resolve_inside(tree: Path, url_path: str, relative: str) -> None:
    """A path inside the folder, encoded or through a link that stays inside, resolves to its file (interfaces: GET /anim/<path>)."""
    assert AnimationFolder(tree).resolve(url_path) == (tree / relative).resolve()


@pytest.mark.parametrize("url_path", OUTSIDE)
def test_resolve_outside_is_403(tree: Path, url_path: str) -> None:
    """A `..`, absolute, encoded, NUL, invalid UTF-8 or symbolic-link path that leaves the folder is refused with 403."""
    with pytest.raises(HttpError) as raised:
        AnimationFolder(tree).resolve(url_path)
    assert raised.value.status == 403


def test_url_of(tree: Path) -> None:
    """Only a file inside the folder gets a `/anim/` URL; a link out of it gets none."""
    folder = AnimationFolder(tree)
    assert folder.url_of(tree / "chapters" / "intro.js") == "/anim/chapters/intro.js"
    assert folder.url_of(tree.parent / "secret.txt") is None
    assert folder.url_of(tree / "leak.txt") is None


def test_folder_must_exist(tmp_path: Path) -> None:
    """The server refuses a folder that does not exist."""
    with pytest.raises(ValueError):
        AnimationFolder(tmp_path / "missing")


def test_version_is_highest_snapshot(tree: Path) -> None:
    """The version is the highest N of the `v<N>/` folders, other names ignored."""
    folder = AnimationFolder(tree)
    assert folder.version() == 0
    for name in ("v1", "v3", "v10", "vx", "v2.bak"):
        (tree / name).mkdir()
    assert folder.version() == 10


@pytest.fixture
def server(tree: Path) -> Iterator[tuple[str, int]]:
    editor = Editor(tree, emit=lambda line: None)
    httpd = serve(editor)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[0], httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def raw_get(address: tuple[str, int], path: str) -> tuple[int, bytes]:
    """GET with the path sent byte for byte, as a hostile client would; http.client does not normalise it."""
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        connection.putrequest("GET", path, skip_accept_encoding=True)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_http_serves_inside(server: tuple[str, int]) -> None:
    """GET /anim/ serves a file inside the folder, with a query string, and 404 for a missing one."""
    assert raw_get(server, "/anim/index.html?t=1.5&reload=2") == (200, b"<html>index</html>")
    assert raw_get(server, "/anim/chapters/intro.js")[0] == 200
    assert raw_get(server, "/anim/missing.js")[0] == 404


@pytest.mark.parametrize("url_path", [p for p in OUTSIDE if "\\" not in p and p])
def test_http_outside_is_403(server: tuple[str, int], url_path: str) -> None:
    """GET /anim/ with a path that leaves the folder, sent unnormalised, answers 403 and no outside content."""
    status, body = raw_get(server, "/anim/" + url_path)
    assert status == 403
    assert b"secret" not in body


def test_http_page_files(server: tuple[str, int]) -> None:
    """The editor page and its assets are served; a path out of `page/` is refused."""
    assert raw_get(server, "/")[0] == 200
    assert raw_get(server, "/page/editor.js")[0] == 200
    assert raw_get(server, "/page/../html_animation_server/folder.py")[0] == 403
    assert raw_get(server, "/page/%2e%2e%2fpyproject.toml")[0] == 403
