import pytest

from ai_models import ConfigError, config


def test_first_colon_splits_the_id():
    assert config.split_id("ollama:gemma4:31b") == ("ollama", "gemma4:31b")


@pytest.mark.parametrize("bad", ["gemma4", ":x", "ollama:"])
def test_id_without_provider_or_model_is_an_error(bad):
    with pytest.raises(ConfigError):
        config.split_id(bad)


def test_model_for_task_and_explicit_id(write_config):
    write_config({"models": {"chat": "ollama:a:1b"}})
    assert config.model_for("chat") == "ollama:a:1b"
    assert config.resolve("openrouter:b", "chat") == "openrouter:b"


def test_missing_task_names_the_config_file(write_config, tmp_path):
    write_config({"models": {"chat": "ollama:a"}})
    with pytest.raises(ConfigError, match="models.music") as e:
        config.model_for("music")
    assert str(tmp_path / "config.yaml") in str(e.value)


def test_missing_file_is_an_error(tmp_path):
    config.use(tmp_path / "none.yaml")
    try:
        with pytest.raises(ConfigError, match="none.yaml"):
            config.load()
    finally:
        config.use(None)


def test_api_key_absent_none_empty_an_error(write_config, tmp_path):
    write_config({})
    assert config.api_key({"kind": "ollama"}) is None
    assert config.api_key({"kind": "openrouter", "api_key": " k "}) == "k"
    for empty in (None, "", " "):
        with pytest.raises(ConfigError, match="openrouter") as e:
            config.api_key({"kind": "openrouter", "api_key": empty})
        assert str(tmp_path / "config.yaml") in str(e.value)


def test_malformed_file_is_an_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    for text in ("a: [", "- a\n- b\n"):
        bad.write_text(text, encoding="utf-8")
        config.use(bad)
        try:
            with pytest.raises(ConfigError, match="bad.yaml"):
                config.load()
        finally:
            config.use(None)


def test_unknown_provider_and_diffusers_model(write_config):
    write_config({"providers": {"p": {"kind": "ollama"}}, "diffusers": {"m": {"steps": 2}}})
    with pytest.raises(ConfigError, match="'q'"):
        config.provider("q")
    with pytest.raises(ConfigError, match="repo"):
        config.diffusers_model("m")
