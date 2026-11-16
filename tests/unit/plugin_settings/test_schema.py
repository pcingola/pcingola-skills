"""The config.yaml schema (`plugin_settings.schema`, docs/plugin_settings.md): what validates, and the YAML path and
reason of each error line (`loader.format_errors`)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from plugin_settings import Config
from plugin_settings.loader import format_errors
from plugin_settings.old_keys import OLD_SETTINGS

TEMPLATE = Path(__file__).resolve().parents[3] / "plugins/setup/skills/settings/assets/config.example.yaml"
KOKORO = {"kind": "kokoro", "model_url": "https://x/m.onnx", "voices_url": "https://x/v.bin", "langs": {"af_": "en-us"}}


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
    assert cfg.model_entry("local:ltx-2.5").missing_video() == []
    assert cfg.model_entry("local:kandinsky-s2v").missing_presenter() == []


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
    assert any(line.startswith("providers.fish.memory_share: replaced by memory") and "Drama 3: 70" in line
               for line in got)


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
    ({"kind": "kokoro", "langs": {"af_": "en-us"}, "voices_url": "https://x/v"},
     "providers.p.model_url: required for kind kokoro"),
    ({**KOKORO, "langs": {}}, "providers.p.langs: Dictionary should have at least 1 item after validation, not 0"),
    ({"kind": "torchaudio"}, "providers.p.url: required for kind torchaudio"),
    ({"kind": "chatterbox", "python": "/py", "url": "https://x"}, "providers.p.files: required for kind chatterbox"),
    ({"kind": "vllm-omni", "python": "/py", "repo": "r", "deploy": "d"},
     "providers.p.memory: required for kind vllm-omni"),
    ({"kind": "vllm-omni", "python": "/py", "repo": "r", "deploy": "d", "memory": 0},
     "providers.p.memory: Input should be greater than 0"),
    ({"kind": "diffusers", "models": {"m": {"steps": 4}}}, "providers.p.models.m.repo: required for kind diffusers"),
    ({"kind": "ollama", "base_url": "localhost:11434"},
     "providers.p.base_url: 'localhost:11434' is not an http:// or https:// URL"),
    ({"kind": "openrouter", "api_key": "  "}, "providers.p.api_key: is empty; set a value or remove the key"),
    ({"kind": "frob"}, "providers.p: kind 'frob' is not one of azure, chatterbox, diffusers, google, kokoro, "
                       "ollama, openai, openrouter, torchaudio, vllm-omni"),
    ({"kind": "google", "api_key": "k", "project": "p"},
     "providers.p: credentials, project and location need vertex: true"),
])
def test_required_and_typed_keys_per_kind(spec, line):
    """Each provider kind's required keys and value types fail at load with the YAML path (the remote kinds' keys:
    tests/unit/ai_models/test_provider_keys.py)."""
    assert line in problems({"providers": {"p": spec}})


def test_image_limits_are_typed():
    """`image` takes integers and a quality of the `Quality` enum; min above max is refused."""
    got = problems({"providers": {"o": {"kind": "openai", "api_key": "k", "models": {
        "a": {"image": {"max_edge": "big"}}, "b": {"image": {"max_edge": 100, "min_edge": 200}},
        "c": {"image": {"max_edge": 100, "default_quality": "best"}}}}}})
    assert "providers.o.models.a.image.max_edge: Input should be a valid integer, unable to parse string as an " \
           "integer" in got
    assert "providers.o.models.b.image: min_edge 200 is above max_edge 100" in got
    assert "providers.o.models.c.image.default_quality: Input should be 'low', 'medium', 'high' or 'auto'" in got


def test_tasks_reference_configured_providers_and_entries():
    """A task naming a provider that is not in providers, or a diffusers model without an entry, fails; a remote
    model needs no entry. Guards a typo in tasks surfacing at the first call instead of at load."""
    got = problems({"providers": {"local": {"kind": "diffusers", "models": {"a": {"repo": "r"}}},
                                  "o": {"kind": "ollama"}},
                    "tasks": {"image": "local:b", "music": "vertex:lyria-002", "chat": "o:any", "video": "local:a"}})
    assert got == ["tasks.image: model 'b' is not in providers.local.models",
                   "tasks.music: provider 'vertex' is not in providers"]
    assert "tasks.chat: model id 'nocolon' is not <provider>:<model>" in problems({"tasks": {"chat": "nocolon"}})


def test_null_sections_take_their_defaults():
    """A section that holds only comments parses as null and takes its defaults."""
    cfg = Config.model_validate({k: None for k in ("providers", "tasks", "network", "huggingface", "brand",
                                                   "studio", "voiceover")})
    assert cfg == Config()


def test_studio_and_brand_values():
    """`studio.dir` must be absolute or start with `~`; `studio.author` collapses whitespace and drops empty
    names; `brand.path` and the path keys expand `~`; `network.no_proxy` is a list."""
    assert "studio.dir: 'Documents/Studio' is not an absolute path or a path starting with ~" in problems(
        {"studio": {"dir": "Documents/Studio"}})
    cfg = Config.model_validate({"studio": {"dir": "~/S", "author": ["  Alice   Example ", "", "Bob"]},
                                 "brand": {"path": ["~/brands", "/b"]}, "network": {"no_proxy": ["localhost"]},
                                 "voiceover": {"voices_dir": "~/v"}})
    assert cfg.studio.author == ["Alice Example", "Bob"] and cfg.studio.path() == Path.home() / "S"
    assert cfg.brand.path == [Path.home() / "brands", Path("/b")]
    assert cfg.voiceover.voices_dir == Path.home() / "v"
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
