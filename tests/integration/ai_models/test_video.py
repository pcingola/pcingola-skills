"""`ai_models.video.animate` with the real LTX-Video 0.9.5 pipeline (Hugging Face cache) on the GPU, at a small
size, few steps and few frames, checked with the real ffprobe (docs/ai_models.md, Video)."""

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

LTX_VIDEO = "Lightricks/LTX-Video-0.9.5"
HAS_GPU = torch.cuda.is_available() or torch.backends.mps.is_available()


@pytest.fixture
def small_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "providers": {"local": {"kind": "diffusers"}}, "models": {"video": "local:ltx-small"},
        "diffusers": {"ltx-small": {"repo": LTX_VIDEO, "pipeline": "LTXImageToVideoPipeline", "steps": 2,
                                    "guidance": 3.0, "fps": 24, "size_multiple": 32, "frame_step": 8,
                                    "width": 128, "height": 96, "max_frames": 9}}}), encoding="utf-8")
    config.use(path)
    yield
    config.use(None)


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_small_ltx_video_clip(small_config, tmp_path):
    """animate turns a 64x84 image into an MP4 of 9 frames (the spec's frame_step 8: 8k+1 covering 0.3 s at
    its 24 fps) at the spec's 128x96, with one H.264 video stream and no audio stream."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 84), (200, 80, 40)).save(buf, format="PNG")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(buf.getvalue(), "a red square", seconds=0.3, seed=1))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout)["streams"]
    assert [(s["codec_type"], s["codec_name"]) for s in streams] == [("video", "h264")]
    assert (streams[0]["width"], streams[0]["height"], int(streams[0]["nb_frames"])) == (128, 96, 9)
