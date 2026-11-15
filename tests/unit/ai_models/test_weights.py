"""`ai_models.weights`: the weights directory of a provider and the download of a missing file."""

from pathlib import Path

import pytest

from ai_models import weights
from ai_models.weights import DownloadError, ensure_file
from tests.settings_env import isolated
from tests.subproc import child_env, py_value, run_python

UNREACHABLE = "http://127.0.0.1:1/model.bin"
MEDIA = Path(__file__).resolve().parents[3] / "plugins" / "media"


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
    """A model's files are in `<dir>/<model lowercased>`."""
    assert weights.model_dir({"dir": "/w"}, "MMS_FA") == Path("/w/mms_fa")


def test_default_dir_is_the_plugin_data_dir(tmp_path):
    """Without `dir`, the weights are in `voiceover/` of the data directory of the plugin that loaded the settings
    (media's for voiceover); a process with no plugin data directory is a `ConfigError` asking for `dir`."""
    imports = (f"import plugin_settings\nplugin = plugin_settings.Plugin.of({str(MEDIA)!r})\nplugin.load()\n"
               "from ai_models import weights")
    env = child_env(CLAUDE_PLUGIN_DATA=str(tmp_path / "pd"))
    assert py_value(imports, "str(weights.root({'kind': 'kokoro'}))", env) == str(tmp_path / "pd" / "voiceover")
    env = isolated()
    env.pop("CLAUDE_PLUGIN_DATA")
    expect = py_value(imports, "str(plugin.data_dir() / 'voiceover')", child_env(env))
    assert py_value(imports, "str(weights.root({'kind': 'kokoro'}))", child_env(env)) == expect
    done = run_python("from ai_models import weights\nweights.root({'kind': 'kokoro'})", child_env(env))
    assert done.returncode == 1 and "set `dir`" in done.stderr
