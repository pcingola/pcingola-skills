"""`ai_models.weights`: the weights directory of a provider and the download of a missing file."""

from pathlib import Path

import pytest

from ai_models import ConfigError, weights
from ai_models.weights import DownloadError, ensure_file
from plugin_settings import KokoroProvider

UNREACHABLE = "http://127.0.0.1:1/model.bin"


def test_connection_error_is_download_error(tmp_path):
    """A refused connection becomes a `DownloadError` with the URL and leaves no `.part` file."""
    dest = tmp_path / "w" / "model.bin"
    with pytest.raises(DownloadError, match=f"cannot download {UNREACHABLE}"):
        ensure_file(UNREACHABLE, dest)
    assert list(dest.parent.iterdir()) == []


def test_existing_file_is_not_downloaded(tmp_path):
    """A file already at its destination is returned without a request."""
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"x")
    assert ensure_file(UNREACHABLE, dest) == dest


def kokoro(**kw) -> KokoroProvider:
    return KokoroProvider(kind="kokoro", **kw)


def test_model_dir_from_the_provider_dir():
    """A model's files are in `<dir>/<model lowercased>`."""
    assert weights.model_dir(kokoro(dir="/w"), "MMS_FA") == Path("/w/mms_fa")


def test_with_dir_defaults_dir():
    """`WeightsDir.with_dir` sets `dir` to the caller's default only when the provider has none, on a copy; without
    either, `weights.root` asks for `dir`."""
    spec = kokoro()
    assert spec.with_dir("/d") == kokoro(dir="/d") and spec.dir is None
    assert kokoro(dir="/own").with_dir("/d").dir == Path("/own")
    with pytest.raises(ConfigError, match="set `dir`"):
        weights.root(spec.with_dir(None))
