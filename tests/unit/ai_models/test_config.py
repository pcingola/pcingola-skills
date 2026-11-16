"""`ai_models.config`: lookups on the typed config (docs/ai_models.md, Config)."""

import pytest

from ai_models import ConfigError, config
from plugin_settings import DiffusersModel, ImageLimits, OllamaProvider, Quality

LOCAL = {"kind": "diffusers", "models": {"m": {"repo": "r/m", "image": {"max_edge": 2048, "min_edge": 256}},
                                         "music": {"repo": "r/a"}}}
AZURE = {"kind": "azure", "base_url": "https://gw.example/az", "api_version": "2025-04-01-preview", "api_key": "k",
         "models": {"gpt-image-2": {"image": {"max_edge": 3840, "max_pixels": 8294400, "always_sized": True,
                                              "default_quality": "high"}}}}


def test_first_colon_splits_the_id():
    """split_id splits a model id at the first colon, so an Ollama tag keeps its own colon."""
    assert config.split_id("ollama:gemma4:31b") == ("ollama", "gemma4:31b")


@pytest.mark.parametrize("bad", ["gemma4", ":x", "ollama:"])
def test_id_without_provider_or_model_is_an_error(bad):
    """split_id refuses an id without a provider or a model part."""
    with pytest.raises(ConfigError, match="<provider>:<model>"):
        config.split_id(bad)


def test_model_for_task_and_explicit_id(write_config):
    """model_for reads `tasks.<task>`; resolve prefers an explicit model id."""
    write_config({"providers": {"ollama": {"kind": "ollama"}}, "tasks": {"chat": "ollama:a:1b"}})
    assert config.model_for("chat") == "ollama:a:1b"
    assert config.resolve("openrouter:b", "chat") == "openrouter:b"


def test_missing_task_names_the_config_file(write_config, tmp_path):
    """A task without a model is a ConfigError naming `tasks.<task>` and the config file."""
    write_config({"providers": {"ollama": {"kind": "ollama"}}, "tasks": {"chat": "ollama:a"}})
    with pytest.raises(ConfigError, match="tasks.music") as e:
        config.model_for("music")
    assert str(tmp_path / "config.yaml") in str(e.value)


def test_missing_file_is_an_error(tmp_path):
    """load refuses a missing config file, naming it (the model layer needs a config)."""
    config.use(tmp_path / "none.yaml")
    try:
        with pytest.raises(ConfigError, match="none.yaml"):
            config.load()
    finally:
        config.use(None)


def test_invalid_file_is_a_config_error_with_every_problem(tmp_path):
    """A file that is not YAML, not a mapping or not valid against the schema is a ConfigError naming the file;
    the schema errors name each YAML path."""
    bad = tmp_path / "bad.yaml"
    for text, message in [("a: [", "is not valid YAML"), ("- a\n- b\n", "must be a mapping"),
                          ("models: {chat: o:x}\nproviders: {o: {kind: openrouter}}\n", "models: renamed to tasks")]:
        bad.write_text(text, encoding="utf-8")
        config.use(bad)
        try:
            with pytest.raises(ConfigError, match=message) as e:
                config.load()
            assert "bad.yaml" in str(e.value)
        finally:
            config.use(None)


def test_provider_and_model_entries(write_config):
    """`provider` returns the typed provider; `model_entry` the model's attributes, None without an entry;
    `diffusers_model` the local model's entry, a ConfigError naming the path to add when missing."""
    write_config({"providers": {"o": {"kind": "ollama"}, "local": LOCAL, "az": AZURE}})
    assert isinstance(config.provider("o"), OllamaProvider)
    with pytest.raises(ConfigError, match="no provider 'q'"):
        config.provider("q")
    assert config.model_entry("o:x") is None
    assert config.model_entry("az:gpt-image-2").image.max_edge == 3840
    assert isinstance(config.diffusers_model("local:m"), DiffusersModel)
    with pytest.raises(ConfigError, match="providers.local.models.zz"):
        config.diffusers_model("local:zz")
    with pytest.raises(ConfigError, match="no diffusers models"):
        config.diffusers_model("o:x")


def test_image_limits(write_config, tmp_path):
    """`image_limits` returns the model's `image` block; a model without one is a ConfigError that names the YAML
    path to add and the keys of its kind."""
    write_config({"providers": {"local": LOCAL, "az": AZURE}})
    assert config.image_limits("local:m") == ImageLimits(max_edge=2048, min_edge=256)
    az = config.image_limits("az:gpt-image-2")
    assert az.always_sized and az.default_quality is Quality.HIGH and az.max_pixels == 8294400
    with pytest.raises(ConfigError) as e:
        config.image_limits("az:dall-e-3")
    assert str(e.value).startswith("az:dall-e-3 has no image limits: add providers.az.models.dall-e-3.image with "
                                   "max_edge (and min_pixels, max_pixels) to ")
    with pytest.raises(ConfigError, match=r"providers.local.models.music.image with max_edge \(and min_edge\)"):
        config.image_limits("local:music")
