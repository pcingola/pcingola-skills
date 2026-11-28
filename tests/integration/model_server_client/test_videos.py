"""`video.animate` and `video.present` of `ai_models` on the model server's tiny video and presenter models through a
provider of kind `openai` (`ai_models.video`; docs/model_server.md, Videos): a job is created, polled and
downloaded; each MP4 is read with PyAV."""

import pytest
import torch
from plugin_settings import DiffusersRole

from ai_models import ConfigError, config, speech, video
from tests.media import clip, png
from tests.integration.model_server_client.conftest import client_id
from tests.prereq import requires
from tests.settings_env import model_entry

NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


def test_video_entry_comes_from_the_server(client):
    """`config.diffusers_model` of the server's video model is the server's entry (tests/config.yaml), so
    `video.clip_size` and `video.frame_count` work on it."""
    spec = config.diffusers_model(client_id("video"), DiffusersRole.VIDEO)
    want = model_entry("video")
    assert (spec.fps, spec.frame_step, spec.max_frames, spec.width, spec.height) == (
        want["fps"], want["frame_step"], want["max_frames"], want["width"], want["height"])
    assert video.frame_count(0.3, spec.fps, spec.frame_step, spec.max_frames) == 9


def test_video_refuses_a_model_of_another_role_or_none(client):
    """The server's image model as a video model, and a model the server lacks, are `ConfigError`s before any
    job."""
    with pytest.raises(ConfigError, match="image model of its server"):
        video.animate(png(64, 64), "waves", seconds=0.3, model=client_id("image"))
    with pytest.raises(ConfigError, match="has no local model"):
        video.animate(png(64, 64), "waves", seconds=0.3, model="srv:diffusers:no-such-model")


@NEEDS_GPU
def test_animate(client):
    """`video.animate` with `aspect` 1 makes an H.264 MP4 at the square size `clip_size` gives from the server's
    entry, with the planned frames and no audio stream."""
    spec = config.diffusers_model(client_id("video"), DiffusersRole.VIDEO)
    w, h = video.clip_size(spec, aspect=1.0)
    got = clip(video.animate(png(64, 84), "waves", seconds=0.3, aspect=1.0))
    assert (got.video_codec, got.width, got.height, got.frames, got.audio_codec) == ("h264", w, h, 9, None)


@NEEDS_GPU
def test_present(client):
    """`video.present` sends the portrait and the narration (the server's speech) as one job: the MP4 is the
    bucket nearest the portrait's aspect, with the narration as an AAC track."""
    narration = speech.speak("Hi.")
    got = clip(video.present(png(64, 96), narration))
    assert (got.width, got.height, got.audio_codec) == (64, 96, "aac")
