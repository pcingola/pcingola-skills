"""The config.yaml schema (`plugin_settings.schema`, docs/plugin_settings.md): what validates, and the YAML path and
reason of each error line (`loader.format_errors`)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from plugin_settings import (Config, DiffusersImageModel, DiffusersMusicModel, DiffusersPresenterModel,
                             DiffusersVideoModel, FishModel)
from plugin_settings.loader import format_errors
from plugin_settings.old_keys import OLD_SETTINGS

TEMPLATE = Path(__file__).resolve().parents[3] / "plugins/setup/skills/settings/assets/config.example.yaml"
KOKORO_MODEL = {"model_url": "https://x/m.onnx", "voices_url": "https://x/v.bin", "langs": {"af_": "en-us"}}
VIDEO = {"repo": "r", "pipeline": "P", "fps": 24, "size_multiple": 32, "frame_step": 8, "width": 64, "height": 64,
         "max_frames": 9}


def problems(data: dict) -> list[str]:
    """The error lines (without the indent) of validating `data`; fails when it is valid."""
    with pytest.raises(ValidationError) as e:
        Config.model_validate(data)
    return [line.strip() for line in format_errors(Path("/c.yaml"), e.value).splitlines()[1:-1]]


def test_template_validates():
    """The setup:settings template is a valid config: every provider, model entry and task of it. Guards the file
    users copy."""
    cfg = Config.model_validate(yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")))
    assert cfg.model_entry("vertex:lyria-002").predict
    assert cfg.model_entry("azure:gpt-image-2").image.always_sized
    assert isinstance(cfg.model_entry("local:flux2-klein-4b"), DiffusersImageModel)
    assert isinstance(cfg.model_entry("local:ace-step-sft"), DiffusersMusicModel)
    assert isinstance(cfg.model_entry("local:ltx-2.5"), DiffusersVideoModel)
    assert isinstance(cfg.model_entry("local:kandinsky-s2v"), DiffusersPresenterModel)
    assert cfg.model_entry("kokoro:kokoro-v1.0").voice == "af_heart"
    assert cfg.model_entry("torchaudio:MMS_FA").url.startswith("https://")


def test_old_layout_lists_every_old_key_with_its_new_path():
    """A file of the earlier layout fails with one line per old section and key, each naming its new place
    (old_keys.py); keys the layout never had are `not a setting`. Guards the migration without a compatibility
    shim (tmp/plans/config_schema.md, migration map)."""
    settings = {k: "x" for k in OLD_SETTINGS} | {"VOICEOVER_KOKORO_VOICE": "af_heart", "VOICEOVER_MODEL_DIR": "/w",
                                                 "DATA_DIR": "/d"}
    got = problems({"providers": {"vertex": {"kind": "google", "api_key": "k", "predict_models": ["lyria-002"]},
                                  "fish": {"kind": "vllm-omni", "memory_share": 0.6}},
                    "models": {"chat": "vertex:g"}, "diffusers": {"m": {"repo": "r"}}, "settings": settings})
    assert "models: renamed to tasks" in got
    assert any(line.startswith("diffusers: moved: each entry is providers.<p>.models.<name>") for line in got)
    for key, text in OLD_SETTINGS.items():
        assert f"settings.{key}: {text}" in got
    assert "settings.DATA_DIR: not a setting" in got
    assert any(line.startswith("settings.VOICEOVER_KOKORO_VOICE: no longer read: the speech and align models are "
                               "tasks.speech and tasks.align") for line in got)
    assert any(line.endswith("give those provider entries dir: /w") for line in got)
    assert "providers.vertex.predict_models: moved: providers.vertex.models.<m>.predict: true for each listed " \
           "model" in got
    assert "providers.fish.memory_share: replaced by providers.fish.models.<m>.memory of kind fish, the GB the " \
           "model takes at its peak" in got


def test_chatterbox_environment_keys_removed():
    """A chatterbox provider of the worker layout (`python`, `start_timeout`, `timeout`) fails at load with the key's
    path and that Chatterbox runs in the caller's process (old_keys.py `OLD_KIND_KEYS`); a provider of another kind
    keeps its `timeout`."""
    got = problems({"providers": {"cb": {"kind": "chatterbox", "python": "/py", "start_timeout": 60, "timeout": 60},
                                  "o": {"kind": "ollama", "timeout": 60}}})
    for key in ("python", "start_timeout", "timeout"):
        assert any(line.startswith(f"providers.cb.{key}: removed: Chatterbox runs in the caller's process")
                   for line in got), got
    assert not any(line.startswith("providers.o.") for line in got), got


def test_vllm_omni_kind_replaced_by_fish():
    """A provider of the removed kind vllm-omni fails at load with one line naming kind fish and the keys that are
    gone (old_keys.py `OLD_KINDS`), not with the list of kinds."""
    got = problems({"providers": {"f": {"kind": "vllm-omni", "python": "/py", "models": {
        "drama-3": {"repo": "fishaudio/drama-3", "deploy": "fish_omni.yaml", "memory": 70}}}}})
    assert len(got) == 1, got
    assert got[0].startswith("providers.f.kind: vllm-omni: replaced by kind fish")
    for key in ("python", "args", "env", "start_timeout", "deploy", "overhead"):
        assert key in got[0], key


def test_fish_model_entry():
    """A fish model entry needs only `repo`; `memory` defaults to Drama 3's peak, 44 GB, `style` to None (no
    instructions), and it takes the voice keys of every speech model; a fish model serves task speech."""
    cfg = Config.model_validate({"providers": {"f": {"kind": "fish", "models": {
        "drama-3": {"repo": "fishaudio/drama-3", "style": "[{instructions}] {text}", "voices": ["default"]},
        "plain": {"repo": "~/models/fish"}}}}, "tasks": {"speech": "f:drama-3"}})
    entry = cfg.model_entry("f:drama-3")
    assert isinstance(entry, FishModel) and entry.memory == 44.0 and entry.voices == ["default"]
    assert entry.style == "[{instructions}] {text}" and cfg.model_entry("f:plain").style is None
    assert "providers.f.models.m.deploy: not a setting of kind fish" in problems(
        {"providers": {"f": {"kind": "fish", "models": {"m": {"repo": "r", "deploy": "d"}}}}})


def test_unknown_section_and_key_fail_with_their_path():
    """A misspelt section, a key a section or provider kind does not have, and an unknown task fail with their
    YAML path."""
    got = problems({"netwrok": {}, "studio": {"dri": "/x"}, "providers": {"o": {"kind": "ollama", "bse_url": "x"}},
                    "tasks": {"chatt": "o:m"}})
    assert "netwrok: not a setting" in got
    assert "studio.dri: not a setting" in got
    assert "providers.o.bse_url: not a setting of kind ollama" in got
    assert any(line.startswith("tasks.chatt: Input should be 'chat'") for line in got)


@pytest.mark.parametrize("spec, line", [
    ({"kind": "kokoro", "models": {"m": {"langs": {"af_": "en-us"}, "voices_url": "https://x/v"}}},
     "providers.p.models.m.model_url: required for kind kokoro"),
    ({"kind": "kokoro", "models": {"m": {**KOKORO_MODEL, "langs": {}}}},
     "providers.p.models.m.langs: Dictionary should have at least 1 item after validation, not 0"),
    ({"kind": "torchaudio", "models": {"MMS_FA": None}}, "providers.p.models.MMS_FA.url: required for kind torchaudio"),
    ({"kind": "chatterbox", "models": {"m": {"url": "https://x"}}},
     "providers.p.models.m.files: required for kind chatterbox"),
    ({"kind": "fish", "models": {"m": {"memory": 44}}}, "providers.p.models.m.repo: required for kind fish"),
    ({"kind": "fish", "models": {"m": {"repo": "r", "memory": 0}}},
     "providers.p.models.m.memory: Input should be greater than 0"),
    ({"kind": "fish", "timeout": 5}, "providers.p.timeout: not a setting of kind fish"),
    ({"kind": "diffusers", "models": {"m": {"steps": 4}}},
     "providers.p.models.m.repo: required for an image model (kind diffusers)"),
    ({"kind": "ollama", "base_url": "localhost:11434"}, "providers.p.base_url: URL scheme should be 'http' or 'https'"),
    ({"kind": "kokoro", "timeout": 5}, "providers.p.timeout: not a setting of kind kokoro"),
    ({"kind": "torchaudio", "timeout": 5}, "providers.p.timeout: not a setting of kind torchaudio"),
    ({"kind": "google", "api_key": "k", "models": {"g": {"image": {"max_edge": 1}}}},
     "providers.p.models.g.image: not a setting of kind google"),
    ({"kind": "kokoro", "model_url": "https://x/m"}, "providers.p.model_url: moved to providers.p.models.<m>.model_url"),
    ({"kind": "openai", "api_key": "k", "voice": "ash"}, "providers.p.voice: moved to providers.p.models.<m>.voice"),
    ({"kind": "openrouter", "api_key": "  "}, "providers.p.api_key: is empty; set a value or remove the key"),
    ({"kind": "frob"}, "providers.p: kind 'frob' is not one of azure, chatterbox, diffusers, fish, google, kokoro, "
                       "ollama, openai, openrouter, torchaudio"),
    ({"kind": "google", "api_key": "k", "project": "p"},
     "providers.p: credentials, project and location need vertex: true"),
])
def test_required_and_typed_keys_per_kind(spec, line):
    """Each provider kind's required keys and value types fail at load with the YAML path (the remote kinds' keys:
    tests/unit/ai_models/test_provider_keys.py)."""
    assert line in problems({"providers": {"p": spec}})


def test_image_limits_are_typed():
    """`image` takes integers and a quality of the `Quality` enum; min above max is refused. An OpenAI-kind model
    needs `max_edge`, `min_pixels` and `max_pixels` and takes no `min_edge`; a diffusers image model needs
    `max_edge` and `min_edge` and takes none of the OpenAI keys (setup:settings SKILL.md, image limits)."""
    px = {"min_pixels": 0, "max_pixels": 10}
    got = problems({"providers": {"o": {"kind": "openai", "api_key": "k", "models": {
        "a": {"image": {"max_edge": "big", **px}}, "b": {"image": {"max_edge": 100, "min_pixels": 20, "max_pixels": 10}},
        "c": {"image": {"max_edge": 100, "default_quality": "best", **px}},
        "d": {"image": {"max_edge": 100, "min_edge": 5, **px}}, "e": {"image": {"max_edge": 100}}}},
        "l": {"kind": "diffusers", "models": {
            "f": {"repo": "r", "image": {"max_edge": 100, "min_edge": 200}},
            "g": {"repo": "r", "image": {"max_edge": 100, "min_edge": 5, "always_sized": True}},
            "h": {"repo": "r", "image": {"max_edge": 100}}}}}})
    assert "providers.o.models.a.image.max_edge: Input should be a valid integer, unable to parse string as an " \
           "integer" in got
    assert "providers.o.models.b.image: min_pixels 20 is above max_pixels 10" in got
    assert "providers.o.models.c.image.default_quality: Input should be 'low', 'medium', 'high' or 'auto'" in got
    assert "providers.o.models.d.image.min_edge: not a setting of kind openai" in got
    assert {"providers.o.models.e.image.min_pixels: required for kind openai",
            "providers.o.models.e.image.max_pixels: required for kind openai"} <= set(got)
    assert "providers.l.models.f.image: min_edge 200 is above max_edge 100" in got
    assert "providers.l.models.g.image.always_sized: not a setting of an image model (kind diffusers)" in got
    assert "providers.l.models.h.image.min_edge: required for an image model (kind diffusers)" in got


def test_diffusers_roles_from_keys():
    """A diffusers entry's role follows its keys (`role_of`): a key of another role is refused and each missing
    required key is named, with the role in the message."""
    got = problems({"providers": {"l": {"kind": "diffusers", "models": {
        "v": {**VIDEO, "inpaint": "X"}, "m": {"repo": "r", "lyrics_arg": "l"},
        "p": {"repo": "r", "pipeline": "P", "fps": 25, "buckets": [[1, 1]], "audio_rate": 1, "output": "o",
              "width": 64}}}}})
    assert got == ["providers.l.models.v.inpaint: not a setting of a video model (kind diffusers)",
                   "providers.l.models.m.duration_arg: required for a music model (kind diffusers)",
                   "providers.l.models.p.width: not a setting of a presenter model (kind diffusers)"]


def test_tasks_reference_configured_providers_and_entries():
    """A task naming a provider that is not in providers, a model of a local kind without an entry, a provider of
    a kind the task does not take (`TASK_KINDS`), or a diffusers model of another role (`TASK_ROLES`) fails; a
    remote model needs no entry; a System-1 model needs a provider with `base_url`. Guards a typo or a wrong model
    in tasks surfacing at the first call instead of at load."""
    got = problems({"providers": {"local": {"kind": "diffusers", "models": {"a": {"repo": "r"}, "v": VIDEO}},
                                  "o": {"kind": "ollama"}, "k": {"kind": "kokoro"},
                                  "or": {"kind": "openrouter", "api_key": "k"}},
                    "tasks": {"image": "local:b", "music": "vertex:lyria-002", "chat": "o:any", "video": "local:a",
                              "presenter": "local:v", "speech": "k:kokoro-v1.0", "align": "o:x", "embed": "local:a",
                              "system1": "or:x", "vision": "o:any"}})
    assert got == ["tasks.image: model 'b' is not in providers.local.models",
                   "tasks.music: provider 'vertex' is not in providers",
                   "tasks.video: providers.local.models.a is an image model; task video takes a video model",
                   "tasks.presenter: providers.local.models.v is a video model; task presenter takes a presenter "
                   "model",
                   "tasks.speech: model 'kokoro-v1.0' is not in providers.k.models",
                   "tasks.align: provider 'o' is of kind ollama; task align takes kinds openai, torchaudio",
                   "tasks.embed: provider 'local' is of kind diffusers; task embed takes kinds azure, google, "
                   "ollama, openai, openrouter",
                   "tasks.system1: provider 'or' has no base_url for System-1 models"]
    assert "tasks.chat: model id 'nocolon' is not <provider>:<model>" in problems({"tasks": {"chat": "nocolon"}})
    assert problems({"tasks": {"speech": None}}) == ["tasks.speech: is empty; give a model or remove the key"]


def test_server_tasks_take_openai_with_a_base_url():
    """Tasks align, music, video and presenter take a model of kind `openai` with a `base_url` (a model server's
    local model, docs/ai_models.md, Provider kinds) and refuse one without (the OpenAI API has no such models)."""
    tasks = {t: "srv:local:m" for t in ("align", "music", "video", "presenter")}
    cfg = Config.model_validate({"providers": {"srv": {"kind": "openai", "base_url": "http://localhost:8000/v1"}},
                                 "tasks": tasks})
    assert cfg.task_model("video") == "srv:local:m"
    got = problems({"providers": {"api": {"kind": "openai", "api_key": "k"}}, "tasks": {"video": "api:sora-2"}})
    assert got == ["tasks.video: provider 'api' has no base_url; task video takes a model of kind openai only from a "
                   "model server"]


def test_null_sections_take_their_defaults():
    """A section, a `models:` map, a model entry or a list that holds only comments parses as null and takes its
    default (empty); a null required key still fails."""
    cfg = Config.model_validate({k: None for k in ("providers", "tasks", "network", "huggingface", "local_models",
                                                   "brand", "studio", "voiceover", "second_opinion")})
    assert cfg == Config()
    cfg = Config.model_validate({"providers": {"o": {"kind": "ollama", "models": None},
                                               "g": {"kind": "google", "api_key": "k", "models": {"lyria-3": None}}},
                                 "brand": {"path": None}, "network": {"no_proxy": None}})
    assert cfg.providers["o"].models == {} and cfg.model_entry("g:lyria-3").predict is False
    assert cfg.brand.path == [] and cfg.network.no_proxy == []
    assert problems({"providers": {"z": {"kind": "azure", "base_url": "https://x", "api_version": None,
                                         "api_key": "k"}}}) == ["providers.z.api_version: Input should be a valid "
                                                                "string"]


def test_studio_and_brand_values():
    """`studio.dir` must be absolute or start with `~`; `studio.author` collapses whitespace and drops empty
    names; `brand.path` and the path keys expand `~`; `network.no_proxy` is a list."""
    assert "studio.dir: 'Documents/Studio' is not an absolute path or a path starting with ~" in problems(
        {"studio": {"dir": "Documents/Studio"}})
    cfg = Config.model_validate({"studio": {"dir": "~/S", "author": ["  Alice   Example ", "", "Bob"]},
                                 "brand": {"path": ["~/brands", "/b"]}, "network": {"no_proxy": ["localhost"]},
                                 "voiceover": {"voices_dir": "~/v"}})
    assert cfg.studio.author == ["Alice Example", "Bob"] and cfg.studio.dir == Path.home() / "S"
    assert Config().studio.dir == Path.home() / "Documents/Studio"
    assert cfg.brand.path == [Path.home() / "brands", Path("/b")]
    assert cfg.voiceover.voices_dir == Path.home() / "v"
    assert Config().second_opinion.codex is False
    assert Config.model_validate({"second_opinion": {"codex": True}}).second_opinion.codex is True
    assert problems({"second_opinion": {"codex": "x"}}) == [
        "second_opinion.codex: Input should be a valid boolean, unable to interpret input"]
    assert "network.no_proxy: Input should be a valid list" in problems({"network": {"no_proxy": "a,b"}})


def test_ca_files_must_exist(tmp_path):
    """`network.extra_ca_cert` and `network.ca_bundle` name existing files (`~` expanded); a missing one fails at
    load instead of being skipped."""
    ca = tmp_path / "ca.pem"
    ca.write_text("pem")
    assert Config.model_validate({"network": {"extra_ca_cert": str(ca)}}).network.extra_ca_cert == ca
    got = problems({"network": {"extra_ca_cert": str(tmp_path / "no.pem"), "ca_bundle": str(tmp_path / "b.pem")}})
    assert got == [f"network.extra_ca_cert: file {tmp_path / 'no.pem'} does not exist",
                   f"network.ca_bundle: file {tmp_path / 'b.pem'} does not exist"]


def test_proxies_are_urls():
    """`network.*_proxy` take URLs with a scheme and keep the text as written (exported unchanged)."""
    cfg = Config.model_validate({"network": {"http_proxy": "http://proxy.example.com:8080",
                                             "all_proxy": "socks5://127.0.0.1:1080"}})
    assert cfg.network.http_proxy == "http://proxy.example.com:8080"
    assert problems({"network": {"https_proxy": "proxy.example.com:8080"}}) == [
        "network.https_proxy: URL scheme should be 'http', 'https', 'socks4', 'socks5' or 'socks5h'"]


def test_lock_wait_is_unset_or_positive():
    """`local_models.lock_wait` is unset by default (no limit on the wait for the local-model lock) or a positive
    number of seconds; zero and negative values fail at load (docs/plugin_settings.md)."""
    assert Config().local_models.lock_wait is None
    assert Config.model_validate({"local_models": {"lock_wait": 1.5}}).local_models.lock_wait == 1.5
    for bad in (0, -1):
        assert problems({"local_models": {"lock_wait": bad}}) == [
            "local_models.lock_wait: Input should be greater than 0"]


def test_model_server_defaults_and_types():
    """`model_server` has its defaults when absent: 127.0.0.1:8000, keep-alive 300 s, Ollama at 127.0.0.1:11434, no
    weights directory; the port is 1 to 65535, keep-alive 0 or more, the Ollama URL an http(s) URL and the weights
    directory absolute (docs/model_server.md, Settings)."""
    s = Config().model_server
    assert (s.host, s.port, s.keep_alive, s.ollama_url, s.weights_dir) == (
        "127.0.0.1", 8000, 300.0, "http://127.0.0.1:11434", None)
    assert Config.model_validate({"model_server": {"keep_alive": 0}}).model_server.keep_alive == 0
    assert problems({"model_server": {"port": 0, "keep_alive": -1, "ollama_url": "localhost:11434",
                                      "weights_dir": "rel/dir", "listen": "x"}}) == [
        "model_server.port: Input should be greater than or equal to 1",
        "model_server.keep_alive: Input should be greater than or equal to 0",
        "model_server.ollama_url: URL scheme should be 'http' or 'https'",
        "model_server.weights_dir: 'rel/dir' is not an absolute path or a path starting with ~",
        "model_server.listen: not a setting"]


def test_memory_on_every_local_model_entry():
    """Every local model entry takes an optional `memory` (GB at its peak), unset by default except fish's (Drama
    3's 44 GB), and a positive number when set; the model server and the load check read it
    (docs/model_server.md, Memory)."""
    entries = {"diffusers": {"m": {"repo": "r", "memory": 12}},
               "kokoro": {"m": {**KOKORO_MODEL, "memory": 1}},
               "chatterbox": {"m": {"url": "https://x", "files": ["f"], "memory": 2.5}},
               "torchaudio": {"m": {"url": "https://x/model.pt", "memory": 1}},
               "fish": {"m": {"repo": "r", "memory": 6}}}
    cfg = Config.model_validate({"providers": {k: {"kind": k, "models": m} for k, m in entries.items()}})
    assert [cfg.model_entry(f"{k}:m").memory for k in entries] == [12, 1, 2.5, 1, 6]
    unset = Config.model_validate({"providers": {"d": {"kind": "diffusers", "models": {"m": {"repo": "r"}}},
                                                 "t": {"kind": "torchaudio", "models": {"m": {"url": "https://x"}}}}})
    assert unset.model_entry("d:m").memory is None and unset.model_entry("t:m").memory is None
    assert problems({"providers": {"d": {"kind": "diffusers", "models": {"m": {"repo": "r", "memory": 0}}}}}) == [
        "providers.d.models.m.memory: Input should be greater than 0"]
