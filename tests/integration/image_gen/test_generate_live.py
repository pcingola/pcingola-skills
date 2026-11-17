"""`image-gen generate` with the `image` and `image_edit` models of tests/config.yaml (real model calls on the tiny
local models): a generation, then an edit of that image."""

import contextlib
import io
import struct
from pathlib import Path

import pytest
from image_gen_tool import cli

from ai_models import config
from tests.settings_env import TEST_CONFIG

PROMPT = "A single red apple on a plain white table, flat illustration, no text"


@pytest.fixture(autouse=True)
def _config():
    """TEST_CONFIG in use for the test."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def generate(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cli.main(["generate", *argv])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def test_generate_then_edit(tmp_path):
    """`generate` writes a PNG with the `image` model, then edits it with `--ref` and `--aspect 3:2` on the
    `image_edit` model; the edit is wider than tall."""
    first = tmp_path / "apple.png"
    code, out, err = generate("--prompt", PROMPT, "--out", str(first))
    assert code == 0, err
    assert out.strip() == str(first)
    assert min(png_size(first)) >= 256

    edited = tmp_path / "apple_green.png"
    code, out, err = generate("--prompt", "Make the apple green", "--ref", str(first), "--out", str(edited),
                              "--aspect", "3:2")
    assert code == 0, err
    w, h = png_size(edited)
    assert w > h
