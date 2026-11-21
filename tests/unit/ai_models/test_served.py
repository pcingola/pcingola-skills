"""`ai_models.served.parse`: a model server's `GET /v1/models/{id}` answer as a `ServedModel` (docs/model_server.md,
Models), and the paths that need no server (docs/ai_models.md, Provider kinds)."""

import pytest
from plugin_settings import DiffusersVideoModel, KokoroModel, ProviderKind, Task

from ai_models import AIModelsError, served, video

VIDEO = DiffusersVideoModel(repo="r", pipeline="P", fps=24, frame_step=8, max_frames=121, width=512, height=320,
                            size_multiple=32)
KOKORO = KokoroModel(model_url="https://x/m.onnx", voices_url="https://x/v.bin", langs={"af_": "en-us"},
                     voice="af_heart")


def answer(kind: str, role: str, entry) -> dict:
    """A local model object of the server's `/v1/models/{id}`."""
    return {"id": "local:m", "object": "model", "created": 0, "owned_by": "local", "kind": kind, "role": role,
            "entry": entry.model_dump(mode="json")}


def test_parse_a_video_model():
    """A diffusers video model's answer becomes a `ServedModel` whose entry is a `DiffusersVideoModel` equal to the
    server's, so `video.clip_size` reads it."""
    m = served.parse("srv:local:m", "local:m", answer("diffusers", "video", VIDEO))
    assert (m.kind, m.role, m.bare, m.entry) == (ProviderKind.DIFFUSERS, Task.VIDEO, "local:m", VIDEO)
    assert video.clip_size(m.entry, aspect=1.0) == video.clip_size(VIDEO, aspect=1.0)


def test_parse_a_speech_model():
    """A kokoro model's answer becomes a `ServedModel` of role speech whose entry is a `KokoroModel`."""
    m = served.parse("srv:kokoro:k", "kokoro:k", answer("kokoro", "speech", KOKORO))
    assert (m.kind, m.role, m.entry.voice) == (ProviderKind.KOKORO, Task.SPEECH, "af_heart")


def test_parse_a_forwarded_model_is_none():
    """An answer without `kind`, `role` and `entry` (Ollama's model object, which the server forwards) is None."""
    assert served.parse("srv:gemma3:270m", "gemma3:270m", {"id": "gemma3:270m", "object": "model"}) is None
    assert served.parse("srv:x", "x", ["not", "an", "object"]) is None


def test_parse_refuses_an_entry_it_cannot_read():
    """An entry its class refuses, or an unknown kind, is an `AIModelsError` naming the model."""
    bad = answer("diffusers", "video", VIDEO)
    del bad["entry"]["fps"]
    with pytest.raises(AIModelsError, match="srv:local:m: the model server describes"):
        served.parse("srv:local:m", "local:m", bad)
    with pytest.raises(AIModelsError, match="srv:local:m"):
        served.parse("srv:local:m", "local:m", {**answer("diffusers", "video", VIDEO), "kind": "nope"})


def test_a_provider_of_another_kind_is_not_served(write_config):
    """A model of a provider of another kind, or of kind `openai` without `base_url`, has no server: `served` is
    None and `kind` is the provider's, with no request."""
    write_config({"providers": {"local": {"kind": "diffusers", "models": {"a": {"repo": "r"}}},
                                "api": {"kind": "openai", "api_key": "k"}}})
    assert served.served("local:a") is None and served.kind("local:a") == "diffusers"
    assert served.served("api:gpt-image-2") is None and served.kind("api:gpt-image-2") == "openai"


def test_parse_keeps_the_voices_of_a_speech_model():
    """A speech model's answer with `voices` keeps the list; `voices` that are not a list of names are an
    `AIModelsError`."""
    data = {**answer("kokoro", "speech", KOKORO), "voices": ["af_heart", "af_bella"]}
    assert served.parse("srv:kokoro:k", "kokoro:k", data).voices == ["af_heart", "af_bella"]
    assert served.parse("srv:kokoro:k", "kokoro:k", answer("kokoro", "speech", KOKORO)).voices is None
    with pytest.raises(AIModelsError, match="voices is not a list"):
        served.parse("srv:kokoro:k", "kokoro:k", {**data, "voices": "af_heart"})
