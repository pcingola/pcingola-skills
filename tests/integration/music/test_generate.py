"""`music generate` with the `music` model of tests/config.yaml (the tiny ACE-Step pipeline, random weights; a real
model call on the GPU)."""

import contextlib
import io
import json
import subprocess
from pathlib import Path

import pytest
from music_tool import cli

from ai_models import config
from tests.settings_env import TEST_CONFIG, task_model


@pytest.fixture(autouse=True)
def _config(tiny_ace_step_folder):
    """TEST_CONFIG in use for the test, with the tiny ACE-Step folder written."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def probe(path: Path) -> tuple[float, str]:
    """The duration in seconds and the codec of the audio stream of `path`, read with ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True, timeout=25).stdout
    info = json.loads(out)
    s = next(s for s in info["streams"] if s["codec_type"] == "audio")
    return float(info["format"]["duration"]), s["codec_name"]


def test_instrumental_with_tempo(tmp_path):
    """`music generate --instrumental --bpm 90 --seconds 6` writes an audio file of the format the model returns,
    with a sidecar recording the model, the prompt sent and the options."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cli.main(["generate", "calm piano", "--instrumental", "--bpm", "90", "--seconds", "6",
                      "-o", str(tmp_path / "a.mp3")])
        except SystemExit as e:
            assert e.code == 0, err.getvalue()
    path = Path(out.getvalue().strip())
    dur, codec = probe(path)
    assert codec in ("mp3", "pcm_s16le")
    assert dur > 5
    meta = json.loads(cli.sidecar(path, ".json").read_text(encoding="utf-8"))
    assert meta["model"] == task_model("music")
    assert meta["options"] == {"instrumental": True, "bpm": 90, "seconds": 6}
    assert "90" in meta["prompt"]
