"""Video jobs of the deployed server (docs/model_server.md, Videos) through `ai_models.video`: `video.animate` with
the tiny LTX-Video and LTX-2 models and `video.present` with the tiny Kandinsky S2V model each create a job, poll it
and download the MP4, read here with PyAV."""

import pytest
from plugin_settings import DiffusersRole

from ai_models import config, speech, video
from tests.media import clip, frames, png
from tests.server.conftest import VIDEO_TIMEOUT_SECONDS, model, task

pytestmark = pytest.mark.timeout(VIDEO_TIMEOUT_SECONDS)
SECONDS = 0.3


def test_animate_with_a_seed():
    """`video.animate` on tasks.video with `aspect` 1 and a seed makes an H.264 MP4 at the square size `clip_size`
    gives from the server's entry, with the planned frames and no audio stream; the same seed gives the same
    frames."""
    spec = config.diffusers_model(task("video"), DiffusersRole.VIDEO)
    w, h = video.clip_size(spec, aspect=1.0)
    n = video.frame_count(SECONDS, spec.fps, spec.frame_step, spec.max_frames)
    first = video.animate(png(64, 84), "waves", seconds=SECONDS, aspect=1.0, seed=7)
    got = clip(first)
    assert (got.video_codec, got.width, got.height, got.frames, got.audio_codec) == ("h264", w, h, n, None)
    again = video.animate(png(64, 84), "waves", seconds=SECONDS, aspect=1.0, seed=7)
    assert frames(again) == frames(first)


def test_animate_with_a_sound_track():
    """`video.animate` with the LTX-2 model makes an MP4 with an AAC sound track."""
    got = clip(video.animate(png(64, 84), "waves", seconds=SECONDS, model=model("ltx2-tiny")))
    assert (got.video_codec, got.audio_codec) == ("h264", "aac")


def test_present():
    """`video.present` on tasks.presenter sends the portrait and the narration (the server's speech) as one job:
    the MP4 is the bucket nearest the portrait's aspect, with the narration as an AAC track."""
    got = clip(video.present(png(64, 96), speech.speak("Hi.")))
    assert (got.width, got.height, got.audio_codec) == (64, 96, "aac")
