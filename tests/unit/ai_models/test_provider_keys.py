"""Unit tests for the keys and endpoints of remote providers: they come only from config.yaml.

The client libraries (OpenAI, Azure OpenAI, google-genai, Pydantic-AI's providers) read
their own environment variables (OPENAI_API_KEY, GOOGLE_API_KEY, ...) for any value
they are not given. Each case runs in a child process with a written config.yaml
(SKILLS_CONFIG) and those variables exported, and checks that they are ignored."""
import pytest

from ai_models import models
from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python

IMPORT = "import asyncio\nfrom ai_models import models, music, system1"
URL = "http://127.0.0.1:9/v1"
# Every variable a client library reads for a key, an endpoint or an API version.
LIBRARY_ENV = {k: "from-env" for k in (
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_AD_TOKEN", "GOOGLE_API_KEY",
    "GEMINI_API_KEY", "OLLAMA_API_KEY", "SYSTEM_ONE_API_KEY", "OPENAI_API_VERSION")}
LIBRARY_ENV.update(OPENAI_BASE_URL="http://from-env.example/v1", AZURE_OPENAI_ENDPOINT="https://from-env.example")
PROVIDERS = {
    "router": {"kind": "openrouter"},
    "api": {"kind": "openai"},
    "keyed": {"kind": "openai", "api_key": "k"},
    "compat": {"kind": "openai", "base_url": URL},
    "az": {"kind": "azure", "base_url": "https://gw.example/az", "api_version": "2025-04-01-preview"},
    "az_nover": {"kind": "azure", "base_url": "https://gw.example/az", "api_key": "k"},
    "az_nourl": {"kind": "azure", "api_version": "2025-04-01-preview", "api_key": "k"},
    "gg": {"kind": "google"},
    "vx": {"kind": "google", "vertex": True, "predict_models": ["lyria-002"]},
    "ol": {"kind": "ollama"},
}


@pytest.fixture
def env(tmp_path) -> dict[str, str]:
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS)
    return child_env({"HOME": str(tmp_path / "home"), "SKILLS_CONFIG": str(cfg), **LIBRARY_ENV})


@pytest.mark.parametrize("name, kind, key", [
    ("router", "openrouter", "api_key"), ("api", "openai", "api_key"), ("az", "azure", "api_key"),
    ("az_nover", "azure", "api_version"), ("az_nourl", "azure", "base_url"), ("gg", "google", "api_key"),
    ("vx", "google", "api_key"),
])
def test_missing_value_is_a_config_error(env, name, kind, key):
    """A provider that needs a key (openrouter, openai without base_url, azure, google, Vertex included) and has
    no `api_key`, or an azure provider without `base_url` or `api_version`, raises ConfigError naming the provider
    and the key, although the client library's variable is exported. Guards config.yaml as the only source."""
    done = run_python(f"{IMPORT}\nmodels.provider({name!r})", env)
    assert done.returncode == 1
    assert f"ConfigError: provider {name!r} of kind {kind} needs `{key}` in " in done.stderr


def test_music_predict_needs_a_key_before_any_request(env):
    """A Vertex predict music model without `api_key` raises ConfigError before the request (the provider's URL
    is the real Vertex endpoint, so a request would fail differently). Guards the Lyria call, which sends the key
    in its own header."""
    done = run_python(f"{IMPORT}\nasyncio.run(music.acompose('calm piano', model='vx:lyria-002'))", env)
    assert done.returncode == 1
    assert "ConfigError: provider 'vx' of kind google needs `api_key`" in done.stderr


def test_keyless_providers_ignore_the_library_variables(env):
    """Ollama, an OpenAI-compatible server with a base_url and System-1 on Ollama get the placeholder key
    models.NO_KEY, not the exported OLLAMA_API_KEY, OPENAI_API_KEY or SYSTEM_ONE_API_KEY. Guards against a client
    library sending a key from the environment."""
    got = py_value(IMPORT, "[models.provider('ol').client.api_key, models.provider('compat').client.api_key, "
                           "system1.system1_model('ol:d3:4b')._provider._api_key, models.NO_KEY]", env)
    assert got[:3] == [got[3]] * 3


def test_openai_without_base_url_uses_the_openai_api(env):
    """An openai provider without base_url talks to the OpenAI API with its own key, not to OPENAI_BASE_URL
    with OPENAI_API_KEY from the environment. Guards the default endpoint."""
    got = py_value(IMPORT, "[str(models.provider('keyed').client.base_url), models.provider('keyed').client.api_key]",
                   env)
    assert got == [models.OPENAI_URL + "/", "k"]
