"""`image-gen generate` with the `image` and `image_edit` models of tests/config.yaml (real model calls on the tiny
local models): a generation, then an edit of that image."""

import struct
from pathlib import Path

from image_gen_tool import cli

from tests.inproc import CliResult, run_main
from tests.settings_env import TEST_CONFIG

PROMPT = "A single red apple on a plain white table, flat illustration, no text"


def generate(*argv: str) -> CliResult:
    """`image-gen generate *argv` in process with the settings of tests/config.yaml."""
    return run_main(cli.main, "generate", *argv, settings=TEST_CONFIG)


def png_size(path: Path) -> tuple[int, int]:
    """(width, height) from the IHDR chunk of the PNG at `path`."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def test_generate_then_edit(tmp_path):
    """`generate` writes a PNG with the `image` model, then edits it with `--ref` and `--aspect 3:2` on the
    `image_edit` model; the edit is wider than tall."""
    first = tmp_path / "apple.png"
    done = generate("--prompt", PROMPT, "--out", str(first))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == str(first)
    assert min(png_size(first)) >= 256

    edited = tmp_path / "apple_green.png"
    done = generate("--prompt", "Make the apple green", "--ref", str(first), "--out", str(edited), "--aspect", "3:2")
    assert done.returncode == 0, done.stderr
    w, h = png_size(edited)
    assert w > h
