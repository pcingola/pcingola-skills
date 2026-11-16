"""Unit tests for the keys, endpoints and headers of remote providers: they come only from config.yaml.

The client libraries (OpenAI, Azure OpenAI, google-genai, Pydantic-AI's providers) read
their own environment variables (OPENAI_API_KEY, OPENAI_CUSTOM_HEADERS, GOOGLE_API_KEY,
...) for any value they are not given. Each case runs in a child process that does what
a skill's CLI does (`plugin_settings.export`, the work of `Plugin.load`, then ai_models)
with a written config.yaml (SKILLS_CONFIG) and those variables exported, and checks that
they are ignored (docs/plugin_settings.md, "Export to the environment")."""
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ai_models import models
from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python

IMPORT = ("import asyncio, os\nimport plugin_settings\nplugin_settings.export()\n"
          "from ai_models import models, music, system1")
URL = "http://127.0.0.1:9/v1"
# Variables the client libraries read for keys, endpoints, API versions, projects and headers.
LIBRARY_ENV = {k: "from-env" for k in (
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_AD_TOKEN", "GOOGLE_API_KEY",
    "GEMINI_API_KEY", "OLLAMA_API_KEY", "SYSTEM_ONE_API_KEY", "OPENAI_API_VERSION", "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID", "OPENROUTER_APP_TITLE", "OPENROUTER_APP_URL", "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI")}
LIBRARY_ENV.update(OPENAI_BASE_URL="http://from-env.example/v1", AZURE_OPENAI_ENDPOINT="https://from-env.example",
                   OPENAI_CUSTOM_HEADERS="Authorization: Bearer from-env\nX-From-Env: 1",
                   GOOGLE_GENAI_DEFAULT_HEADERS='{"X-From-Env": "1"}', GOOGLE_APPLICATION_CREDENTIALS="/from-env.json")
# Headers a client adds from those variables.
ENV_HEADERS = ("OpenAI-Organization", "OpenAI-Project", "HTTP-Referer", "X-Title", "X-From-Env")
AZURE = {"kind": "azure", "base_url": "https://gw.example/az", "api_version": "2025-04-01-preview"}
PROVIDERS = {
    "router_k": {"kind": "openrouter", "api_key": "rk"},
    "keyed": {"kind": "openai", "api_key": "ok"},
    "compat": {"kind": "openai", "base_url": URL},
    "az_k": {**AZURE, "api_key": "ak"},
    "vx_project": {"kind": "google", "vertex": True, "project": "p1", "location": "europe-west4",
                   "models": {"lyria-002": {"predict": True}}},
    "ol": {"kind": "ollama"},
}
# Providers that lack a value their kind requires, and the error line of each (config.yaml fails at load).
INVALID = [
    ({"kind": "openrouter"}, "providers.p.api_key: required for kind openrouter"),
    ({"kind": "openai"}, "providers.p.api_key: required for kind openai without base_url (the OpenAI API)"),
    (AZURE, "providers.p.api_key: required for kind azure"),
    ({"kind": "azure", "base_url": "https://gw.example/az", "api_key": "k"},
     "providers.p.api_version: required for kind azure"),
    ({"kind": "azure", "api_version": "2025-04-01-preview", "api_key": "k"},
     "providers.p.base_url: required for kind azure"),
    ({"kind": "google"}, "providers.p.api_key: required for kind google"),
    ({"kind": "google", "vertex": True},
     "providers.p.api_key: required for kind google (or credentials, project or location for Google Cloud "
     "credentials)"),
]


@pytest.fixture
def env(tmp_path) -> dict[str, str]:
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS)
    return child_env({"HOME": str(tmp_path / "home"), "SKILLS_CONFIG": str(cfg), **LIBRARY_ENV})


@pytest.mark.parametrize("spec, line", INVALID)
def test_missing_value_fails_at_load(tmp_path, spec, line):
    """A provider that needs a key (openrouter, openai without base_url, azure, google; Vertex without Google
    Cloud credentials) and has no `api_key`, or an azure provider without `base_url` or `api_version`, makes
    the export of a skill's start (`plugin_settings.export`) exit 1 with the YAML path of the missing value,
    although the client library's variable is exported. Guards config.yaml as the only source (setup:settings,
    provider kinds)."""
    cfg = write_config(tmp_path / "config.yaml", providers={"p": spec})
    done = run_python(IMPORT, child_env({"HOME": str(tmp_path / "home"), "SKILLS_CONFIG": str(cfg), **LIBRARY_ENV}))
    assert done.returncode == 1
    assert f"\n  {line}\n" in done.stderr, done.stderr


def test_music_predict_needs_a_key_before_any_request(env):
    """A Vertex predict music model (Lyria) with Google Cloud credentials and no `api_key` raises ConfigError
    before the request, since the predict call authenticates with the key. Guards the Lyria call, which sends the
    key in its own header."""
    done = run_python(f"{IMPORT}\nasyncio.run(music.acompose('calm piano', model='vx_project:lyria-002'))", env)
    assert done.returncode == 1
    assert "ConfigError: provider 'vx_project'" in done.stderr and "`api_key`" in done.stderr


@pytest.mark.parametrize("name, auth", [
    ("ol", f"Bearer {models.NO_KEY}"), ("compat", f"Bearer {models.NO_KEY}"), ("keyed", "Bearer ok"),
    ("router_k", "Bearer rk"), ("az_k", "Bearer ak"),
])
def test_client_headers_come_from_the_config(env, name, auth):
    """The real client of each OpenAI-family kind sends the config key (models.NO_KEY for a provider that needs
    none) in Authorization, and none of the headers a library builds from its variables (organization, project,
    OpenRouter title and referer, OPENAI_CUSTOM_HEADERS, which would also replace Authorization). The headers
    sent are the client's auth_headers overridden by its default_headers, without the omitted (non-string) ones.
    Guards against a key or header from the shell."""
    headers = py_value(IMPORT, f"(lambda c: {{**c.auth_headers, **{{k: v for k, v in c.default_headers.items() "
                               f"if isinstance(v, str)}}}})(models.provider({name!r}).client)", env)
    assert headers.get("Authorization") == auth
    assert not set(ENV_HEADERS) & set(headers)


def test_openai_without_base_url_uses_the_openai_api(env):
    """An openai provider without base_url talks to the OpenAI API with its own key, not to OPENAI_BASE_URL
    with OPENAI_API_KEY from the environment. Guards the default endpoint."""
    got = py_value(IMPORT, "[str(models.provider('keyed').client.base_url), models.provider('keyed').client.api_key]",
                   env)
    assert got == [models.OPENAI_URL + "/", "ok"]


def test_system1_key_is_the_placeholder(env):
    """System-1 on a keyless Ollama provider gets models.NO_KEY, not SYSTEM_ONE_API_KEY from the environment.
    Guards the bearer token of System-1 requests."""
    assert py_value(IMPORT, "system1.system1_model('ol:d3:4b').provider.api_key", env) == models.NO_KEY


def test_library_variables_are_removed(env):
    """After export, no variable of plugin_settings.CLEARED_PREFIXES or CLEARED_KEYS is left, so neither the
    clients nor child processes see one. Guards the variables a client reads that no constructor argument covers
    (GOOGLE_GENAI_DEFAULT_HEADERS, GOOGLE_APPLICATION_CREDENTIALS, ...)."""
    left = py_value(IMPORT, f"[k for k in {sorted(LIBRARY_ENV)!r} if k in os.environ]", env)
    assert left == []


def service_account(path) -> str:
    """Write a service-account JSON file with a fresh RSA key at `path`; return its path."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    path.write_text(json.dumps({
        "type": "service_account", "project_id": "sa-project", "private_key_id": "1", "private_key": pem,
        "client_email": "sa@sa-project.iam.gserviceaccount.com", "client_id": "1",
        "token_uri": "https://oauth2.googleapis.com/token"}), encoding="utf-8")
    return str(path)


def test_vertex_with_google_cloud_credentials(tmp_path):
    """A Vertex provider without `api_key` builds a Vertex client from a service-account file (`credentials`) or
    from `project` and `location` (Application Default Credentials). Guards the Vertex path that needs no key
    (setup:settings, provider kinds)."""
    cfg = write_config(tmp_path / "config.yaml", providers={
        "sa": {"kind": "google", "vertex": True, "credentials": service_account(tmp_path / "sa.json")},
        "adc": {"kind": "google", "vertex": True, "project": "p1", "location": "europe-west4"}})
    env = child_env({"HOME": str(tmp_path / "home"), "SKILLS_CONFIG": str(cfg), **LIBRARY_ENV})
    assert py_value(IMPORT, "[models.provider(n).client.vertexai for n in ('sa', 'adc')]", env) == [True, True]


@pytest.mark.parametrize("name, status, named", [
    ("compat", 401, True), ("ol", 403, True), ("keyed", 401, False), ("vx_project", 403, False),
    ("compat", 500, False),
])
def test_refusal_of_a_keyless_provider_names_the_key(write_config, name, status, named):
    """`explained` turns a 401 or 403 from a provider without `api_key` (and without Google Cloud credentials)
    into an AIModelsError naming providers.<name>.api_key and the config file; a provider with a key, Vertex with
    credentials and other statuses keep the library's error. The error is Pydantic-AI's real ModelHTTPError.
    Guards an OpenAI-compatible server that checks a key, now that no key comes from the shell."""
    from pydantic_ai.exceptions import ModelHTTPError

    from ai_models import AIModelsError, config
    from ai_models.errors import explained

    write_config({"providers": PROVIDERS})
    with pytest.raises(Exception) as e:
        with explained(f"{name}:m"):
            raise ModelHTTPError(status, "m", {"error": "denied"})
    if named:
        assert type(e.value) is AIModelsError
        assert f"set providers.{name}.api_key in {config.path()}" in str(e.value)
    else:
        assert type(e.value) is ModelHTTPError
