"""`ai_models.video.animate` and `present` with the tiny random-weight video models of tests/config.yaml on the
GPU, at a small size, few steps and few frames, checked with the real ffprobe (docs/ai_models.md, Video)."""

import io
import json
import shutil
import subprocess

import pytest
import torch
from PIL import Image
from plugin_settings import DiffusersRole

from ai_models import config, local, video
from tests.media import frames
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG

# The tests/config.yaml entry of the LTX-2 model, whose pipeline generates a sound track with the frames.
LTX2 = "local:ltx2-tiny"
HAS_GPU = torch.cuda.is_available() or torch.backends.mps.is_available()


@pytest.fixture(autouse=True)
def _config():
    """TEST_CONFIG in use for the test."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def streams(clip) -> list[dict]:
    """The streams of the MP4 `clip`, read with ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True, timeout=25)
    return json.loads(out.stdout)["streams"]


def red_png(width: int, height: int) -> bytes:
    """A PNG of a red-orange `width` x `height` image."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_small_ltx_video_clip(tmp_path):
    """animate with the `video` model turns a 64x84 image into an MP4 of 9 frames (the spec's frame_step 8: 8k+1
    covering 0.3 s at its 24 fps) at the spec's 128x96, with one H.264 video stream and no audio stream: LTX-Video
    0.9.5 generates no sound track (docs/ai_models.md, Video)."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(red_png(64, 84), "a red square", seconds=0.3, seed=1))
    found = streams(clip)
    assert [(s["codec_type"], s["codec_name"]) for s in found] == [("video", "h264")]
    assert (found[0]["width"], found[0]["height"], int(found[0]["nb_frames"])) == (128, 96, 9)


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
def test_seeded_ltx_clip_repeats():
    """animate with the `video` model and a seed draws its noise from a torch generator on the pipeline's device
    (`local.pipe_kwargs`): LTX-Video's decode noise (`torch.randn` with the generator on the device) takes it, and
    the same seed gives the same frames (docs/ai_models.md, Video)."""
    first, again = (frames(video.animate(red_png(64, 84), "a red square", seconds=0.3, seed=7)) for _ in range(2))
    assert len(first) == 9 and first == again
    kwargs = local.pipe_kwargs(config.diffusers_model(config.model_for("video"), DiffusersRole.VIDEO), {"seed": 7})
    assert kwargs["generator"].device.type == local.device()


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_ltx2_clip_carries_its_sound_track(tmp_path):
    """animate with an LTX-2 model writes the pipeline's `audio` output (`waveform`) as an AAC stream at the
    vocoder's output rate (`local.audio_rate`: 24 kHz, not the transformer's 16 kHz `audio_sampling_rate`) with the
    vocoder's two channels, as long as the 9 frames at 24 fps within 50 ms (an audio latent covers 40 ms, plus AAC
    framing). On MPS its transformer and text connectors load with `rope_double_precision` false
    (`local.DEVICE_CONFIG`: MPS has no float64) (docs/ai_models.md, Video)."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(red_png(64, 84), "a red square", seconds=0.3, model=LTX2, seed=1))
    found = {s["codec_type"]: s for s in streams(clip)}
    assert (found["video"]["codec_name"], found["video"]["width"], found["video"]["height"]) == ("h264", 128, 96)
    assert int(found["video"]["nb_frames"]) == 9
    spec = config.diffusers_model(LTX2, DiffusersRole.VIDEO)
    rate = local.audio_rate(local.pipeline(spec.repo, cls=spec.pipeline, skip=spec.skip))  # the cached pipeline
    assert (found["audio"]["codec_name"], int(found["audio"]["sample_rate"]), found["audio"]["channels"]) == \
        ("aac", rate, 2)
    assert rate == 24000
    assert float(found["audio"]["duration"]) == pytest.approx(9 / 24, abs=0.05)
    pipe = local.pipeline(spec.repo, cls=spec.pipeline, skip=spec.skip)
    double = local.DEVICE_CONFIG.get(local.device(), {}).get("rope_double_precision", True)
    assert [pipe.transformer.config.rope_double_precision, pipe.connectors.config.rope_double_precision] == \
        [double, double]


@requires(HAS_GPU, f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_quantized_modular_clip(tmp_path, tiny_minimax_h3_folder):
    """animate with a ModularPipeline video model (`minimax-h3-tiny`: MiniMax-H3, random weights) whose `quantize`
    names the transformer: every linear weight of the transformer holds int8 data on the device (torchao), the text
    encoder keeps plain bfloat16 weights, and the clip is an MP4 at the spec's 64x64 from the pipeline's `videos`
    output, 124 frames (frame_step 17 gives 120, which MiniMax-H3 rounds up to 17 * 7 + 5), with its `audio` output as
    a stereo AAC stream at 32 kHz (docs/ai_models.md, Video)."""
    model = "local:minimax-h3-tiny"
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video.animate(red_png(80, 60), "a red square", seconds=5, model=model, seed=1))
    found = {s["codec_type"]: s for s in streams(clip)}
    assert (found["video"]["codec_name"], found["video"]["width"], found["video"]["height"]) == ("h264", 64, 64)
    assert int(found["video"]["nb_frames"]) == 124
    assert (found["audio"]["codec_name"], int(found["audio"]["sample_rate"]), found["audio"]["channels"]) == \
        ("aac", 32000, 2)
    spec = config.diffusers_model(model, DiffusersRole.VIDEO)
    pipe = local.pipeline(spec.repo, cls=spec.pipeline, skip=spec.skip, quantize=spec.quantize)  # the cached one
    linears = [m.weight for m in pipe.transformer.modules() if isinstance(m, torch.nn.Linear)]
    assert linears and all(w.qdata.dtype == torch.int8 and w.device.type == local.device() for w in linears)
    text = [m.weight for m in pipe.text_encoder.modules() if isinstance(m, torch.nn.Linear)]
    assert text and all(type(w) is torch.nn.Parameter and w.dtype == torch.bfloat16 for w in text)


@requires(HAS_GPU, f"local presenter models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
@requires(shutil.which("ffprobe"), "ffprobe (FFmpeg) not installed")
def test_tiny_presenter_clip(tmp_path):
    """present loads the `presenter` model, a ModularPipeline class (`load_components`, through the lock and memory
    check), and turns a 60x100 portrait and 1.5 s of 24 kHz mono speech into an MP4 in the bucket nearest the 9:16
    aspect (64x96), 37 frames at 25 fps (the speech's length, cut to whole frames), with an AAC track at the
    speech's 24 kHz."""
    import wave

    import numpy as np

    speech = io.BytesIO()
    with wave.open(speech, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.sin(np.arange(36000) * 2 * np.pi * 220 / 24000) * 8000).astype(np.int16).tobytes())
    clip = tmp_path / "presenter.mp4"
    clip.write_bytes(video.present(red_png(60, 100), speech.getvalue(), aspect=9 / 16, seed=1))
    found = {s["codec_type"]: s for s in streams(clip)}
    assert (found["video"]["codec_name"], found["video"]["width"], found["video"]["height"]) == ("h264", 64, 96)
    assert int(found["video"]["nb_frames"]) == 37
    assert (found["audio"]["codec_name"], int(found["audio"]["sample_rate"])) == ("aac", 24000)
    spec = config.diffusers_model(config.model_for("presenter"), DiffusersRole.PRESENTER)
    assert any(type(p).__name__ == spec.pipeline for p in local._pipes.values())
