"""Routing of a request's `model` (`model_server.model_ref.ModelRef`, docs/model_server.md, Routing) against the
providers of tests/config.yaml, read as a `Config`; no model is loaded."""

import pytest
from plugin_settings import Config, ProviderKind

from model_server.model_ref import ModelRef, ollama_prefix
from model_server.model_role import ModelRole
from model_server.route import Route
from model_server.server_error import ServerError
from tests.settings_env import config_sections, kind_model, task_model

CFG = Config.model_validate(config_sections())


def test_local_provider_routes_in_process():
    """`<provider>:<model>` of a local provider runs in process, with its kind, entry and role: the role of a
    diffusers entry, speech for the speech kinds, align for torchaudio; `test` is its provider's (true for every
    local provider of tests/config.yaml, false by default)."""
    roles = {task_model("image"): ModelRole.IMAGE, task_model("video"): ModelRole.VIDEO,
             task_model("presenter"): ModelRole.PRESENTER, task_model("music"): ModelRole.MUSIC,
             task_model("speech"): ModelRole.SPEECH, kind_model("chatterbox"): ModelRole.SPEECH,
             kind_model("fish"): ModelRole.SPEECH, task_model("align"): ModelRole.ALIGN}
    for model_id, role in roles.items():
        ref = ModelRef.parse(model_id, CFG)
        assert (ref.route, ref.role, ref.id, ref.test) == (Route.LOCAL, role, model_id, True)
        assert ref.entry is CFG.model_entry(model_id)
    assert ModelRef.parse(task_model("image"), CFG).kind == ProviderKind.DIFFUSERS
    plain = Config.model_validate({"providers": {"d": {"kind": "diffusers", "models": {"m": {"repo": "r"}}}}})
    assert ModelRef.parse("d:m", plain).test is False


def test_ollama_prefix_routes_to_ollama_by_tag():
    """`<prefix>:<tag>` goes to Ollama with the tag after the first colon; the prefix is the name of the config's
    provider of kind `ollama` (`ollama` in tests/config.yaml), `ollama` when the config has none."""
    for model, tag in (("ollama:gemma3:270m", "gemma3:270m"), ("ollama:all-minilm", "all-minilm"),
                       (task_model("system1"), task_model("system1").split(":", 1)[1])):
        ref = ModelRef.parse(model, CFG)
        assert (ref.route, ref.id, ref.tag, ref.provider, ref.role) == (Route.OLLAMA, model, tag, "ollama", None)
    renamed = Config.model_validate({"providers": {"oll": {"kind": "ollama"}}})
    assert (ollama_prefix(renamed), ollama_prefix(Config()), ollama_prefix(CFG)) == ("oll", "ollama", "ollama")
    assert ModelRef.parse("oll:gemma3:270m", renamed).tag == "gemma3:270m"
    assert ModelRef.parse(task_model("image"), CFG).tag is None


def test_bare_tag_and_unknown_provider_are_404():
    """A bare Ollama tag, an empty tag and an id of a provider that is neither local nor the Ollama prefix are a 404
    `model_not_found` whose message names the prefixed form."""
    for model, named in (("gemma3:270m", "ollama:gemma3:270m"), ("all-minilm", "ollama:all-minilm"),
                         ("ollama:", "ollama:ollama:"), ("openrouter:x", "ollama:openrouter:x")):
        with pytest.raises(ServerError) as e:
            ModelRef.parse(model, CFG)
        assert (e.value.status, e.value.error.code, e.value.error.param) == (404, "model_not_found", "model")
        assert named in str(e.value), str(e.value)


def test_unknown_local_model_and_missing_model():
    """A local provider without the named model is a 404 `model_not_found`; a missing or empty `model` is a 400."""
    with pytest.raises(ServerError) as e:
        ModelRef.parse("diffusers:no-such-model", CFG)
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
                       (ModelRef.parse("ollama:gemma3:270m", CFG), (ModelRole.SPEECH,))):
        with pytest.raises(ServerError) as e:
            ref.require(*roles)
        assert e.value.status == 400 and ref.id in str(e.value)


def test_parallel_gpu_and_memory():
    """Ollama models and the torchaudio aligner run requests in parallel, the other local kinds one at a time;
    diffusers and fish load to the GPU; `memory` is the entry's GB in bytes, None when unset."""
    refs = {m: ModelRef.parse(m, CFG) for m in (task_model("image"), task_model("speech"), task_model("align"),
                                                kind_model("fish"), "ollama:gemma3:270m")}
    assert [r.parallel for r in refs.values()] == [False, False, True, False, True]
    assert [r.gpu for r in refs.values()] == [True, False, False, True, False]
    assert refs[kind_model("fish")].memory == 6 * 10**9
    assert refs[task_model("image")].memory is None and refs["ollama:gemma3:270m"].memory is None
