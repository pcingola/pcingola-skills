"""`ai_models.weights`: the weights directory of a provider and the download of a missing file."""

from pathlib import Path

import pytest

from ai_models import weights
from ai_models.weights import DownloadError, ensure_file

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


def test_model_dir_from_the_provider_dir():
    """A model's files are in `<dir>/<model lowercased>`; without `dir`, under the `ai-models` cache."""
    assert weights.model_dir({"dir": "/w"}, "MMS_FA") == Path("/w/mms_fa")
    assert weights.model_dir({}, "kokoro-v1.0").parent.name == weights.CACHE_NAME
