"""`music generate` with the `music` model of tests/config.yaml (the tiny ACE-Step pipeline, random weights; a real
model call on the GPU), through `music_tool.cli.main(argv)` in process, so one call checks the printed path an agent
reads and the files the command writes."""

import json
import subprocess
from pathlib import Path

import pytest
from music_tool import cli

from tests.inproc import run_main
from tests.settings_env import TEST_CONFIG, task_model

pytestmark = pytest.mark.usefixtures("tiny_ace_step_folder")


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
    done = run_main(cli.main, "generate", "calm piano", "--instrumental", "--bpm", "90", "--seconds", "6",
                    "-o", str(tmp_path / "a.mp3"), settings=TEST_CONFIG)
    assert done.returncode == 0, done.stderr
    path = Path(done.stdout.strip())
    dur, codec = probe(path)
    assert codec in ("mp3", "pcm_s16le")
    assert dur > 5
    meta = json.loads(cli.sidecar(path, ".json").read_text(encoding="utf-8"))
    assert meta["model"] == task_model("music")
    assert meta["options"] == {"instrumental": True, "bpm": 90, "seconds": 6}
    assert "90" in meta["prompt"]
