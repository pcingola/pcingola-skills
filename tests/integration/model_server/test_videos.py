"""`POST /v1/videos`, `GET /v1/videos/{id}` and `GET /v1/videos/{id}/content` of the model server
(docs/model_server.md, Videos) on the tiny random-weight video and presenter models of tests/config.yaml, in process
on the GPU, through the `openai` SDK; each MP4 is read with PyAV."""

import openai
import pytest
import torch
from openai.types import Video

from tests.media import clip, finished, frames, png
from tests.prereq import requires
from tests.settings_env import entry, task_model
from tests.wav import read

NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local video models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
LTX2 = "local:ltx2-tiny"


@NEEDS_GPU
def test_video_job(running):
    """A video job of the `video` model: created queued with the clip's planned length and size, completed, and
    its content is an H.264 MP4 at the model's size with the planned frames (8k+1 covering 0.3 s at 24 fps) and no
    audio stream (LTX-Video 0.9.5 makes none). Its content before it completes is a 409 `video_not_ready`."""
    model = task_model("video")
    spec = entry(model)
    job = running.client.videos.create(model=model, prompt="waves", seconds="0.3",
                                       input_reference=("still.png", png(64, 84), "image/png"))
    assert job.status == "queued" and job.size == f"{spec['width']}x{spec['height']}" and job.seconds == "0.375"
    with pytest.raises(openai.APIStatusError) as e:
        running.client.videos.download_content(job.id)
    assert (e.value.status_code, e.value.code) == (409, "video_not_ready")
    done = finished(running.client, job)
    assert done.status == "completed" and done.progress == 100, done.error
    got = clip(running.client.videos.download_content(done.id).content)
    assert (got.video_codec, got.width, got.height, got.frames, got.audio_codec) == (
        "h264", spec["width"], spec["height"], 9, None)


@NEEDS_GPU
def test_seeded_video_jobs_repeat(running):
    """Two jobs of the `video` model with the same `seed` (an `extra_body` field) complete on the server's GPU, its
    generator on the pipeline's device, and give the same frames."""
    def run() -> list[bytes]:
        job = running.client.videos.create(model=task_model("video"), prompt="waves", seconds="0.3",
                                           input_reference=("still.png", png(64, 84), "image/png"),
                                           extra_body={"seed": 7})
        done = finished(running.client, job)
        assert done.status == "completed", done.error
        return frames(running.client.videos.download_content(done.id).content)

    first = run()
    assert len(first) == 9 and first == run()


@NEEDS_GPU
def test_ltx2_job_with_size_has_a_sound_track(running):
    """A job of the LTX-2 model with `size` makes the clip at that size, with the sound track the pipeline
    generates (an AAC stream)."""
    job = running.client.videos.create(model=LTX2, prompt="rain", seconds="0.3", size="96x64",
                                       input_reference=("still.png", png(64, 64), "image/png"))
    done = finished(running.client, job)
    assert done.status == "completed", done.error
    got = clip(running.client.videos.download_content(done.id).content)
    assert (got.width, got.height, got.audio_codec) == (96, 64, "aac")


@NEEDS_GPU
def test_presenter_job_with_narration(running):
    """A presenter job takes the portrait (`input_reference`) and the narration (`audio`, a multipart field
    outside the SDK's params, sent with `client.post`): the clip is the model's bucket nearest `aspect`, as long as
    the narration, with it as an AAC sound track."""
    speech = running.client.audio.speech.create(model=task_model("speech"), input="Hi.", voice="af_heart",
                                                response_format="wav").content
    files = [("input_reference", ("face.png", png(64, 96), "image/png")), ("audio", ("say.wav", speech, "audio/wav"))]
    job = running.client.post("/videos", cast_to=Video, body={"model": task_model("presenter"), "prompt": "",
                                                              "aspect": 1.0},
                              files=files, options={"headers": {"Content-Type": "multipart/form-data"}})
    assert job.size == "64x64" and abs(float(job.seconds) - read(speech).seconds) < 0.01
    done = finished(running.client, job)
    assert done.status == "completed", done.error
    got = clip(running.client.videos.download_content(done.id).content)
    assert (got.width, got.height, got.audio_codec) == (64, 64, "aac")


def test_video_errors(running):
    """A presenter job without `audio`, a video model without `input_reference` and an unknown job are OpenAI
    errors, raised before any model loads."""
    with pytest.raises(openai.BadRequestError) as e:
        running.client.videos.create(model=task_model("presenter"), prompt="",
                                     input_reference=("face.png", png(64, 64), "image/png"))
    assert e.value.param == "audio"
    with pytest.raises(openai.BadRequestError) as e:
        running.client.videos.create(model=task_model("video"), prompt="waves")
    assert e.value.param == "input_reference"
    with pytest.raises(openai.NotFoundError):
        running.client.videos.retrieve("video_none")
