"""`References`, the reference recordings of speech requests (docs/model_server.md, Speech): one file per recording,
named by its content, the most recent `KEEP` kept, and a 400 naming `reference_audio` for a malformed field."""

import base64

import pytest

from model_server.references import KEEP, References
from model_server.server_error import ServerError


def field(data: bytes, fmt: str = "wav") -> dict:
    """A `reference_audio` value of `data`."""
    return {"data": base64.b64encode(data).decode(), "format": fmt}


def test_one_file_per_recording_and_the_last_kept():
    """The same bytes name the same file, which holds them; after `KEEP` other recordings the first one's file is
    gone; `close` removes the directory."""
    refs = References()
    try:
        first = refs.path(field(b"one"))
        assert refs.path(field(b"one")) == first and first.read_bytes() == b"one" and first.suffix == ".wav"
        for i in range(KEEP):
            refs.path(field(f"other {i}".encode(), "flac"))
        assert not first.exists() and len(list(refs.dir.iterdir())) == KEEP
    finally:
        refs.close()
    assert not refs.dir.exists()


@pytest.mark.parametrize("value", ["abc", {"data": "AAAA"}, {"data": "AAAA", "format": "ogg"},
                                   {"data": "not base64!", "format": "wav"}, {"data": "", "format": "wav"}])
def test_malformed_field_is_a_400(value):
    """A value that is not `{"data": <base64>, "format": wav | mp3 | flac}` with some bytes is a 400 on
    `reference_audio`."""
    refs = References()
    try:
        with pytest.raises(ServerError) as e:
            refs.path(value)
        assert (e.value.status, e.value.error.param) == (400, "reference_audio")
    finally:
        refs.close()
