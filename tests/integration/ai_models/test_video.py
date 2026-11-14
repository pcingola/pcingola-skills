"""`ai_models.video.animate` with the real tiny random LTX-2 pipeline (11 MB, Hugging Face cache) on the GPU,
checked with the real ffprobe (docs/ai_models.md, Video)."""

import io
import json
import shutil
import subprocess

import pytest
import torch
import yaml
from PIL import Image

from ai_models import config, video
from tests.prereq import requires

TINY_LTX2 = "optimum-intel-internal-testing/tiny-random-ltx2"
HAS_GPU = torch.cuda.is_available() or torch.backends.mps.is_available()


@pytest.fixture
def tiny_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "providers": {"local": {"kind": "diffusers"}}, "models": {"video": "local:tiny-ltx2"},
        "diffusers": {"tiny-ltx2": {"repo": TINY_LTX2, "pipeline": "LTX2ImageToVideoPipeline", "steps": 2,
                                    "fps": 24, "size_multiple": 32, "frame_step": 8, "width": 64, "height": 64,
                                    "max_frames": 9}}}), encoding="utf-8")
    config.use(path)
    yield
    config.use(None)


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_tiny_ltx2_clip(tiny_config, tmp_path):
    """animate turns a 64x84 image into an MP4 of 9 frames (the spec's frame_step 8: 8k+1 covering 0.3 s at
    its 24 fps) at the spec's 64x64, with one H.264 video stream and no audio stream."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 84), (200, 80, 40)).save(buf, format="PNG")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(buf.getvalue(), "a red square", seconds=0.3, seed=1))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout)["streams"]
    assert [(s["codec_type"], s["codec_name"]) for s in streams] == [("video", "h264")]
    assert (streams[0]["width"], streams[0]["height"], int(streams[0]["nb_frames"])) == (64, 64, 9)
