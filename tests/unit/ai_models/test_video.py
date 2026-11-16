"""`ai_models.video`: the frame and size rules and the model resolution (docs/ai_models.md, Video)."""

import pytest

from ai_models import AIModelsError, ConfigError, video
from plugin_settings import DiffusersVideoModel


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


SPEC = DiffusersVideoModel(repo="r", pipeline="P", fps=24, frame_step=8, max_frames=121, width=512, height=320,
                           size_multiple=32)


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
    """A video model without one of the required keys fails at load, naming each missing key."""
    write_config({"providers": {"local": {"kind": "diffusers", "models": {
        "v": {"repo": "r", "pipeline": "P", "width": 64, "height": 64}}}}, "tasks": {"video": "local:v"}})
    with pytest.raises(ConfigError) as e:
        video.animate(b"", "p", seconds=1.0)
    for key in ("fps", "size_multiple", "frame_step", "max_frames"):
        assert f"providers.local.models.v.{key}: required for a video model (kind diffusers)" in str(e.value)


def test_model_resolves_from_task_video(write_config):
    """animate takes the model of task `video`; a config without the task, a model of another kind and a
    diffusers model of another role are a ConfigError."""
    write_config({"providers": {"ollama": {"kind": "ollama"}, "local": {"kind": "diffusers", "models": {
        "i": {"repo": "r"}}}}, "tasks": {}})
    with pytest.raises(ConfigError, match="tasks.video"):
        video.animate(b"", "p", seconds=1.0)
    with pytest.raises(ConfigError, match="task video takes kinds diffusers"):
        video.animate(b"", "p", seconds=1.0, model="ollama:x")
    with pytest.raises(ConfigError, match="is an image model; task video takes a video model"):
        video.animate(b"", "p", seconds=1.0, model="local:i")


def test_model_failure_is_one_line(write_config):
    """A failure inside the video pipeline (here a `pipeline` class diffusers does not have) is an AIModelsError
    with a one-line message that names the model, not the library's exception. Guards the one-line error
    media:short-video and Studio report for an `Engine: video` scene."""
    write_config({"providers": {"local": {"kind": "diffusers", "models": {
        "v": {"repo": "r", "pipeline": "NoSuchPipeline", "fps": 24, "size_multiple": 32, "frame_step": 8, "width": 64,
              "height": 64, "max_frames": 9}}}}, "tasks": {"video": "local:v"}})
    with pytest.raises(AIModelsError) as e:
        video.animate(b"", "p", seconds=1.0)
    assert type(e.value) is AIModelsError and "\n" not in str(e.value)
    assert str(e.value).startswith("local:v: AttributeError")


BUCKETS = [[512, 512], [512, 768], [768, 512]]


def test_bucket_is_nearest_aspect():
    """bucket picks the [width, height] nearest the requested aspect on a log scale: 16:9 and 4:3 take the wide
    bucket, 9:16 the tall one, 1:1 the square one. Guards a presenter clip of a 16:9 film made in a tall frame."""
    assert video.bucket(BUCKETS, 16 / 9) == (768, 512)
    assert video.bucket(BUCKETS, 4 / 3) == (768, 512)
    assert video.bucket(BUCKETS, 9 / 16) == (512, 768)
    assert video.bucket(BUCKETS, 1.0) == (512, 512)


def test_missing_presenter_keys_are_named(write_config):
    """A presenter model without a required key fails at load, naming each missing key; so does `buckets` that is
    not a list of [width, height]."""
    p = {"repo": "r", "pipeline": "P", "fps": 25, "output": "videos"}
    write_config({"providers": {"local": {"kind": "diffusers", "models": {"p": p}}}, "tasks": {"presenter": "local:p"}})
    with pytest.raises(ConfigError) as e:
        video.present(b"", b"")
    for key in ("buckets", "audio_rate"):
        assert f"providers.local.models.p.{key}: required for a presenter model (kind diffusers)" in str(e.value)
    q = {**p, "buckets": [[512]], "audio_rate": 16000}
    write_config({"providers": {"local": {"kind": "diffusers", "models": {"q": q}}}})
    with pytest.raises(ConfigError, match=r"providers.local.models.q.buckets\[0\]"):
        video.present(b"", b"", model="local:q")


def test_presenter_resolves_from_task_presenter(write_config):
    """present takes the model of task `presenter`; a model of another kind and a config without the task are a
    ConfigError."""
    write_config({"providers": {"ollama": {"kind": "ollama"}}, "tasks": {"presenter": "ollama:x"}})
    with pytest.raises(ConfigError, match="task presenter takes kinds diffusers"):
        video.present(b"", b"")
    write_config({"providers": {"local": {"kind": "diffusers"}}, "tasks": {}})
    with pytest.raises(ConfigError, match="tasks.presenter"):
        video.present(b"", b"")
