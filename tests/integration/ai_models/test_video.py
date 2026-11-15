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
    its 24 fps) at the spec's 128x96, with one H.264 video stream and no audio stream: LTX-Video 0.9.5 generates no
    sound track (docs/ai_models.md, Video)."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 84), (200, 80, 40)).save(buf, format="PNG")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(buf.getvalue(), "a red square", seconds=0.3, seed=1))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout)["streams"]
    assert [(s["codec_type"], s["codec_name"]) for s in streams] == [("video", "h264")]
    assert (streams[0]["width"], streams[0]["height"], int(streams[0]["nb_frames"])) == (128, 96, 9)


TINY_S2V = "kandinskylab/tiny-kandinsky-s2v-distilled-modular-pipe"


@pytest.fixture
def presenter_config(tmp_path):
    """The tiny random-weight Kandinsky S2V modular pipeline of the diffusers tests (32 MB). Its text RoPE has 128
    positions, so the prompt is short."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "providers": {"local": {"kind": "diffusers"}}, "models": {"presenter": "local:s2v-tiny"},
        "diffusers": {"s2v-tiny": {"repo": TINY_S2V, "pipeline": "KandinskyS2VDistilledModularPipeline", "steps": 2,
                                   "fps": 25, "buckets": [[64, 64], [64, 96], [96, 64]], "audio_rate": 16000,
                                   "output": "videos", "args": {"prompt": "A person speaks."}}}}), encoding="utf-8")
    config.use(path)
    yield
    config.use(None)


@requires(HAS_GPU, f"local presenter models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_tiny_presenter_clip(presenter_config, tmp_path):
    """present loads a ModularPipeline class (`load_components`, through the lock and memory check) and turns a
    60x100 portrait and 1.5 s of 24 kHz mono speech into an MP4 in the bucket nearest the 9:16 aspect (64x96), 37
    frames at 25 fps (the speech's length, cut to whole frames), with an AAC track at the speech's 24 kHz."""
    import wave

    import numpy as np

    from ai_models import local

    img = io.BytesIO()
    Image.new("RGB", (60, 100), (200, 80, 40)).save(img, format="PNG")
    speech = io.BytesIO()
    with wave.open(speech, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.sin(np.arange(36000) * 2 * np.pi * 220 / 24000) * 8000).astype(np.int16).tobytes())
    clip = tmp_path / "presenter.mp4"
    clip.write_bytes(video.present(img.getvalue(), speech.getvalue(), aspect=9 / 16, seed=1))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True)
    streams = {s["codec_type"]: s for s in json.loads(out.stdout)["streams"]}
    assert (streams["video"]["codec_name"], streams["video"]["width"], streams["video"]["height"]) == ("h264", 64, 96)
    assert int(streams["video"]["nb_frames"]) == 37
    assert (streams["audio"]["codec_name"], int(streams["audio"]["sample_rate"])) == ("aac", 24000)
    assert any(type(p).__name__ == "KandinskyS2VDistilledModularPipeline" for p in local._pipes.values())
