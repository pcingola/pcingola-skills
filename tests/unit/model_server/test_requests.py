"""Request parsing of the model server: sizes, typed bodies and their extra fields, the model of a forwarded body,
the rewriting of a forwarded `model`, error bodies, video jobs and the model list (docs/model_server.md, Endpoints
and Errors); no model runs."""

import time

import pytest
from openai.types import Model
from openai.types.audio import SpeechCreateParams
from openai.types.image_generate_params import ImageGenerateParamsNonStreaming
from plugin_settings import Config

from model_server.catalog import local_models, model_object, ollama_object
from model_server.forms import checked, extras, form_value, parse_size
from model_server.model_ref import ModelRef
from model_server.model_role import ModelRole
from model_server.music_create_params import MusicCreateParams
from model_server.ollama import line_with_model, rewritten, with_model
from model_server.routes_ollama import body_model
from model_server.server_error import ErrorType, ServerError
from model_server.video_job import VideoJob, VideoStatus
from model_server.video_jobs import VideoJobs
from tests.settings_env import config_sections, task_model


def test_parse_size():
    """`WxH` gives (width, height), `auto` and None give None; anything else is a 400 on `size`."""
    assert parse_size("512x256") == (512, 256) and parse_size("auto") is None and parse_size(None) is None
    for bad in ("512", "0x5", "axb", "512x"):
        with pytest.raises(ServerError) as e:
            parse_size(bad)
        assert (e.value.status, e.value.error.param) == (400, "size")


def test_checked_body_keeps_extra_fields():
    """A body is checked against its OpenAI params type (a wrong field is a 400 naming it), and the fields outside
    the type are the extra arguments of the model (`extra_body`)."""
    body = {"model": "diffusers:m", "prompt": "a cat", "n": 1, "seed": 3, "guidance_scale": 2.0}
    assert checked(ImageGenerateParamsNonStreaming, body) is body
    assert extras(ImageGenerateParamsNonStreaming, body) == {"seed": 3, "guidance_scale": 2.0}
    assert extras(SpeechCreateParams, {"model": "k:m", "input": "hi", "speaker": "bob"}, "speaker") == {}
    with pytest.raises(ServerError) as e:
        checked(MusicCreateParams, {"model": "diffusers:m", "prompt": "p", "seconds": "long"})
    assert (e.value.status, e.value.error.param) == (400, "seconds")
    with pytest.raises(ServerError) as e:
        checked(MusicCreateParams, {"model": "diffusers:m"})
    assert e.value.error.param == "prompt"


def test_form_value_and_body_model():
    """A multipart text field reads as JSON when it parses, else as text; a forwarded body's `model` is read from a
    JSON object only."""
    assert (form_value("3"), form_value("1.5"), form_value("true"), form_value("a cat")) == (3, 1.5, True, "a cat")
    assert body_model(b'{"model": "gemma3:270m", "stream": true}') == "gemma3:270m"
    assert body_model(b"") is None and body_model(b"[1]") is None and body_model(b"not json") is None


def test_answer_model_is_the_client_id():
    """The `model` of a forwarded JSON object is rewritten (the tag in a request body, the client's id in an
    answer): a JSON body as a whole, server-sent events and NDJSON line by line across chunk boundaries with their
    line endings, `[DONE]` and objects without `model` unchanged, another media type untouched."""
    import asyncio
    import json

    assert json.loads(with_model(b'{"model": "ollama:gemma3:270m", "stream": true}', "gemma3:270m")) == {
        "model": "gemma3:270m", "stream": True}
    assert with_model(b'{"data": []}', "x") == b'{"data": []}' and with_model(b"[1]", "x") == b"[1]"
    assert line_with_model(b'data: {"model":"g"}\r\n', "ollama:g") == b'data: {"model":"ollama:g"}\r\n'
    assert line_with_model(b"data: [DONE]\n", "x") == b"data: [DONE]\n" and line_with_model(b"\n", "x") == b"\n"

    async def collect(chunks, media_type):
        async def source():
            for c in chunks:
                yield c
        return b"".join([c async for c in rewritten(source(), media_type, "ollama:g")])

    sse = [b'data: {"model":"g","n":1}\n\ndata: {"mo', b'del":"g","n":2}\n\ndata: [DONE]\n\n']
    assert asyncio.run(collect(sse, "text/event-stream")) == (
        b'data: {"model":"ollama:g","n":1}\n\ndata: {"model":"ollama:g","n":2}\n\ndata: [DONE]\n\n')
    assert asyncio.run(collect([b'{"model":"g"}\n{"model"', b':"g","done":true}'], "application/x-ndjson")) == (
        b'{"model":"ollama:g"}\n{"model":"ollama:g","done":true}')
    assert asyncio.run(collect([b'{"model":', b'"g"}'], "application/json")) == b'{"model":"ollama:g"}'
    assert asyncio.run(collect([b'{"model":"g"}'], "text/plain")) == b'{"model":"g"}'


def test_ollama_object_has_the_server_id_kind_and_role():
    """An Ollama model in the model list keeps Ollama's fields, with the server's id, kind `ollama` and its role
    when known."""
    data = {"id": "gemma3:270m", "object": "model", "created": 5, "owned_by": "library"}
    assert ollama_object(data, "ollama:gemma3:270m", ModelRole.CHAT) == {
        **data, "id": "ollama:gemma3:270m", "kind": "ollama", "role": "chat"}
    assert "role" not in ollama_object(data, "ollama:gemma3:270m", None)


def test_error_body_is_openai_style():
    """An error answers `{"error": {"message", "type", "param", "code"}}` with its status."""
    r = ServerError(507, "no room", ErrorType.INSUFFICIENT_MEMORY, "insufficient_memory").response()
    assert r.status_code == 507
    assert r.body == (b'{"error":{"code":"insufficient_memory","message":"no room",'
                      b'"param":null,"type":"insufficient_memory_error","misalignment":null}}')


def test_video_job_lifecycle_and_expiry():
    """A job is queued, then in progress, then completed with its MP4 or failed with an error; as
    `openai.types.Video` it keeps a local model's size and length; it is dropped `ttl` seconds after it ends."""
    jobs = VideoJobs(ttl=60)
    job = jobs.add(VideoJob("diffusers:v", "waves", "0.375", "128x96"))
    assert jobs.get(job.id).video().status == "queued"
    job.start()
    job.complete(b"mp4", 60)
    video = job.video()
    assert (video.status, video.progress, video.size, video.seconds) == ("completed", 100, "128x96", "0.375")
    assert video.expires_at == video.completed_at + 60
    failed = jobs.add(VideoJob("diffusers:v", "", "1", "64x64"))
    failed.fail("model_error", "boom", 60)
    assert failed.status == VideoStatus.FAILED and failed.video().error.message == "boom"
    job.expires_at = int(time.time()) - 1
    with pytest.raises(ServerError) as e:
        jobs.get(job.id)
    assert e.value.status == 404


def test_local_models_list_entry_attributes():
    """Every model of a local provider of the config is listed as `openai.types.Model` with its kind, role and
    config entry, from which a client reads a video model's frame counts and size, and its provider's `test`
    (docs/model_server.md, Models); the Ollama models are not local."""
    models = {m.id: m for m in local_models(Config.model_validate(config_sections()))}
    video = models[task_model("video")]
    assert isinstance(video, Model) and video.owned_by == task_model("video").split(":")[0]
    assert (video.kind, video.role) == ("diffusers", "video")
    sections = config_sections()["providers"]["diffusers"]["models"]["ltx-tiny"]
    assert {k: video.entry[k] for k in ("fps", "frame_step", "max_frames", "width", "height")} == {
        k: sections[k] for k in ("fps", "frame_step", "max_frames", "width", "height")}
    assert models[task_model("presenter")].entry["buckets"] == [[64, 64], [64, 96], [96, 64]]
    assert models[task_model("align")].role == "align" and models[task_model("speech")].role == "speech"
    assert all(m.test for m in models.values()) and task_model("chat") not in models


def test_model_object_carries_voices_when_given():
    """One speech model's object has `voices` when the route gives them, and no `voices` field otherwise
    (docs/model_server.md, Models)."""
    ref = ModelRef.parse(task_model("speech"), Config.model_validate(config_sections()))
    assert model_object(ref, ["af_heart", "af_bella"]).voices == ["af_heart", "af_bella"]
    assert "voices" not in model_object(ref).model_dump()
