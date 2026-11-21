"""Routing of a request's `model` (`model_server.model_ref.ModelRef`, docs/model_server.md, Routing) against the
providers of tests/config.yaml, read as a `Config`; no model is loaded."""

import pytest
from plugin_settings import Config, ProviderKind

from model_server.model_ref import ModelRef
from model_server.model_role import ModelRole
from model_server.route import Route
from model_server.server_error import ServerError
from tests.settings_env import config_sections, kind_model, task_model

CFG = Config.model_validate(config_sections())


def test_local_provider_routes_in_process():
    """`<provider>:<model>` of a local provider runs in process, with its kind, entry and role: the role of a
    diffusers entry, speech for the speech kinds, align for torchaudio."""
    roles = {task_model("image"): ModelRole.IMAGE, task_model("video"): ModelRole.VIDEO,
             task_model("presenter"): ModelRole.PRESENTER, task_model("music"): ModelRole.MUSIC,
             task_model("speech"): ModelRole.SPEECH, kind_model("chatterbox"): ModelRole.SPEECH,
             kind_model("fish"): ModelRole.SPEECH, task_model("align"): ModelRole.ALIGN}
    for model_id, role in roles.items():
        ref = ModelRef.parse(model_id, CFG)
        assert (ref.route, ref.role, ref.id) == (Route.LOCAL, role, model_id)
        assert ref.entry is CFG.model_entry(model_id)
    assert ModelRef.parse(task_model("image"), CFG).kind == ProviderKind.DIFFUSERS


def test_other_ids_go_to_ollama_unchanged():
    """An Ollama tag (its colon included), a bare name and an id of the config's `ollama` provider, which is not a
    local kind, go to Ollama as written."""
    for model in ("gemma3:270m", "all-minilm", "ollama:gemma3:270m", "laya:421m-english-bf16"):
        ref = ModelRef.parse(model, CFG)
        assert (ref.route, ref.id, ref.role) == (Route.OLLAMA, model, None)


def test_unknown_local_model_and_missing_model():
    """A local provider without the named model is a 404 `model_not_found`; a missing or empty `model` is a 400."""
    with pytest.raises(ServerError) as e:
        ModelRef.parse("local:no-such-model", CFG)
    assert (e.value.status, e.value.error.code, e.value.error.param) == (404, "model_not_found", "model")
    for model in (None, "", "  ", 3):
        with pytest.raises(ServerError) as e:
            ModelRef.parse(model, CFG)
        assert e.value.status == 400


def test_require_role():
    """An endpoint takes only local models of its roles: another role or an Ollama model is a 400 naming the
    model."""
    image = ModelRef.parse(task_model("image"), CFG)
    assert image.require(ModelRole.IMAGE) is image
    for ref, roles in ((image, (ModelRole.VIDEO, ModelRole.PRESENTER)),
                       (ModelRef.parse("gemma3:270m", CFG), (ModelRole.SPEECH,))):
        with pytest.raises(ServerError) as e:
            ref.require(*roles)
        assert e.value.status == 400 and ref.id in str(e.value)


def test_parallel_gpu_and_memory():
    """Ollama models and the torchaudio aligner run requests in parallel, the other local kinds one at a time;
    diffusers and fish load to the GPU; `memory` is the entry's GB in bytes, None when unset."""
    refs = {m: ModelRef.parse(m, CFG) for m in (task_model("image"), task_model("speech"), task_model("align"),
                                                kind_model("fish"), "gemma3:270m")}
    assert [r.parallel for r in refs.values()] == [False, False, True, False, True]
    assert [r.gpu for r in refs.values()] == [True, False, False, True, False]
    assert refs[kind_model("fish")].memory == 6 * 10**9
    assert refs[task_model("image")].memory is None and refs["gemma3:270m"].memory is None
