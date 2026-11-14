"""`ai_models.video`: the frame and size rules and the model resolution (docs/ai_models.md, Video)."""

import pytest

from ai_models import AIModelsError, ConfigError, video



def test_frame_count_is_step_k_plus_1_and_covers_the_request():
    """frame_count gives the smallest step*k+1 count (k >= 1) that covers seconds * fps."""
    assert video.frame_count(3.0, 24, 8, 1000) == 73  # 72 frames wanted
    assert video.frame_count(2.9, 24, 8, 1000) == 73  # 69.6 -> 70 wanted -> 73
    assert video.frame_count(0.01, 24, 8, 1000) == 9  # at least one step
    assert video.frame_count(1.0, 10, 4, 1000) == 13  # 10 wanted -> 13


def test_frame_count_capped_by_max_frames():
    """frame_count cuts a long request to max_frames, rounded down to the step*k+1 form."""
    assert video.frame_count(10.0, 24, 8, 121) == 121
    assert video.frame_count(10.0, 24, 8, 100) == 97


def test_frame_size_rounds_to_multiple():
    """frame_size rounds each side to the nearest multiple, at least the multiple."""
    assert video.frame_size(640, 360, 32) == (640, 352)
    assert video.frame_size(10, 100, 32) == (32, 96)
    assert video.frame_size(70, 100, 16) == (64, 96)


SPEC = {"width": 512, "height": 320, "size_multiple": 32}


def test_clip_size_defaults_to_the_model_size():
    """clip_size is the model's `width` and `height` without arguments, and the caller's size when given, rounded
    to `size_multiple` (docs/ai_models.md, Video)."""
    assert video.clip_size(SPEC) == (512, 320)
    assert video.clip_size(SPEC, 1920, 1080) == (1920, 1088)


def test_clip_size_reshapes_the_model_size_to_the_aspect():
    """clip_size with `aspect` keeps the model's pixel count in that width / height ratio. Guards a 16:9 project
    making a small video model render at the 1920x1080 project size."""
    assert video.clip_size(SPEC, aspect=16 / 9) == (544, 288)
    assert video.clip_size(SPEC, aspect=9 / 16) == (288, 544)
    assert video.clip_size(SPEC, aspect=1.0) == (416, 416)


def test_missing_video_keys_are_named(write_config):
    """A video model without one of the required keys is a ConfigError that names each missing key."""
    write_config({"providers": {"local": {"kind": "diffusers"}}, "models": {"video": "local:v"},
                  "diffusers": {"v": {"repo": "r", "pipeline": "P", "width": 64, "height": 64}}})
    with pytest.raises(ConfigError, match="lacks fps, size_multiple, frame_step, max_frames"):
        video.video_spec("v")


def test_model_resolves_from_task_video(write_config):
    """animate takes the model of task `video`; a provider kind other than diffusers and a config without
    the task are a ConfigError."""
    write_config({"providers": {"ollama": {"kind": "ollama"}}, "models": {"video": "ollama:x"}})
    with pytest.raises(ConfigError, match="no video models"):
        video.animate(b"", "p", seconds=1.0)
    write_config({"providers": {"local": {"kind": "diffusers"}}, "models": {}})
    with pytest.raises(ConfigError, match="models.video"):
        video.animate(b"", "p", seconds=1.0)


def test_model_failure_is_one_line(write_config):
    """A failure inside the video pipeline (here a `pipeline` class diffusers does not have) is an AIModelsError
    with a one-line message that names the model, not the library's exception. Guards the one-line error
    media:short-video and Studio report for an `Engine: video` scene."""
    write_config({"providers": {"local": {"kind": "diffusers"}}, "models": {"video": "local:v"},
                  "diffusers": {"v": {"repo": "r", "pipeline": "NoSuchPipeline", "fps": 24, "size_multiple": 32,
                                      "frame_step": 8, "width": 64, "height": 64, "max_frames": 9}}})
    with pytest.raises(AIModelsError) as e:
        video.animate(b"", "p", seconds=1.0)
    assert type(e.value) is AIModelsError and "\n" not in str(e.value)
    assert str(e.value).startswith("local:v: AttributeError")
