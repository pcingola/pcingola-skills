"""A failed weight download is one `DownloadError` naming the URL, and the CLI prints it as one error line."""

import pytest

from voiceover_tool.download import DownloadError, ensure_file

from .cli_run import voiceover

UNREACHABLE = "http://127.0.0.1:1/model.bin"


def test_connection_error_is_download_error(tmp_path):
    """A refused connection becomes a `DownloadError` with the URL and leaves no `.part` file."""
    dest = tmp_path / "w" / "model.bin"
    with pytest.raises(DownloadError, match=f"cannot download {UNREACHABLE}"):
        ensure_file(UNREACHABLE, dest, 10)
    assert list(dest.parent.iterdir()) == []


def test_setup_failure_is_one_error_line(tmp_path):
    """The proxy at a closed local port makes every download fail without reaching the network; the weight URLs
    come from the settings file."""
    proxy = "http://127.0.0.1:1"
    config = tmp_path / "config.yaml"
    config.write_text(f"settings:\n  VOICEOVER_KOKORO_MODEL_URL: {UNREACHABLE}\n"
                      f"  VOICEOVER_KOKORO_VOICES_URL: {UNREACHABLE}\n"
                      f"  VOICEOVER_ALIGNER: MMS_FA\n  VOICEOVER_ALIGNER_URL: {UNREACHABLE}\n")
    p = voiceover("setup", SKILLS_CONFIG=str(config), VOICEOVER_MODEL_DIR=str(tmp_path / "w"), HTTPS_PROXY=proxy, https_proxy=proxy,
                  HTTP_PROXY=proxy, http_proxy=proxy, ALL_PROXY=proxy, all_proxy=proxy, NO_PROXY="", no_proxy="")
    assert p.returncode == 1, p.stderr
    assert "Traceback" not in p.stderr
    assert f"Error: cannot download {UNREACHABLE}" in p.stderr
