"""Unit tests of the studio server's path helpers, slugs, safe names and data URLs."""
from __future__ import annotations

import base64
import threading
from pathlib import Path

import pytest

from studio_server.paths import (HttpError, decode_data_url, inside, png_size, resolve_abs, safe_name, slug,
                                 write_atomic, write_new)

from .conftest import png


def test_slug():
    """Names become lowercase ASCII words joined by `-`. Guards the directory of a new project."""
    assert slug("My Café: Poster #2!") == "my-cafe-poster-2"
    assert slug("  --A__B--  ") == "a-b"
    assert slug("!!!") == ""
    assert len(slug("x" * 200)) == 40


def test_safe_name():
    """A reference name keeps only its last component and safe characters. Guards writes outside refs/."""
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("C:\\x\\photo of me.JPG") == "photo-of-me.JPG"
    assert safe_name(".hidden") == "hidden"
    assert safe_name("..") == "ref"
    assert safe_name("") == "ref"


def test_resolve_abs_rejects_relative(tmp_path: Path):
    """Relative paths, empty strings, NUL bytes and non-strings are 400. Guards resolution against the cwd."""
    for bad in ("images/x", "", "/a\0b", None, 3):
        with pytest.raises(HttpError) as e:
            resolve_abs(bad, "path")
        assert e.value.status == 400
    assert resolve_abs(str(tmp_path / "a" / ".." / "b"), "path") == tmp_path.resolve() / "b"


def test_inside_follows_links(tmp_path: Path):
    """A link inside the base pointing outside resolves outside. Guards symlink escapes."""
    base = (tmp_path / "base")
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)
    assert inside((base / "x").resolve(), base.resolve())
    assert not inside((base / "link" / "x").resolve(), base.resolve())
    assert not inside((tmp_path / "base2").resolve(), base.resolve())


def test_decode_data_url():
    """Base64 data URLs of an allowed type decode; others are 400. Guards /api/marked and /api/refs input."""
    url = "data:image/png;base64," + base64.b64encode(b"abc").decode()
    assert decode_data_url(url, ("image/png",)) == ("image/png", b"abc")
    for bad in ("data:image/png,abc", "data:image/gif;base64,YWJj", "data:image/png;base64,***", "abc", None,
                "data:image/png;base64,"):
        with pytest.raises(HttpError):
            decode_data_url(bad, ("image/png",))


def test_png_size():
    """png_size reads width and height from the IHDR chunk and is None for other bytes. Guards the mask size check."""
    assert png_size(png(640, 480)) == (640, 480)
    assert png_size(png(3, 7, alpha=True)[:24]) == (3, 7)
    assert png_size(png(3, 7)[:23]) is None
    assert png_size(b"GIF89a" + bytes(30)) is None


def test_write_new_numbers(tmp_path: Path):
    """A taken name gets -2, -3; a dangling link at the name is not followed. Guards overwrites."""
    assert write_new(tmp_path, "a.png", b"1").name == "a.png"
    assert write_new(tmp_path, "a.png", b"2").name == "a-2.png"
    (tmp_path / "b.png").symlink_to(tmp_path / "nowhere")
    assert write_new(tmp_path, "b.png", b"3").name == "b-2.png"
    assert not (tmp_path / "nowhere").exists()


def test_write_new_numbered(tmp_path: Path):
    """With numbered, names are <stem>-1, -2 from the first. Guards the marked copies' names."""
    assert write_new(tmp_path, "v1-marked.png", b"1", numbered=True).name == "v1-marked-1.png"
    assert write_new(tmp_path, "v1-marked.png", b"2", numbered=True).name == "v1-marked-2.png"


def test_write_atomic_concurrent(tmp_path: Path):
    """Threads writing one file at once each succeed, the file holds one whole write and no temporary file is
    left. Guards the shared temporary name."""
    target = tmp_path / "project.json"
    errors = []

    def write(i: int) -> None:
        try:
            for _ in range(50):
                write_atomic(target, str(i).encode() * 100)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    data = target.read_bytes()
    assert len(data) == 100 and len(set(data)) == 1
    assert [f.name for f in tmp_path.iterdir()] == ["project.json"]
