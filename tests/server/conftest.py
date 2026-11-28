"""Tests of a deployed model server (`lib/model_server`) over the network, run only by
`scripts/tests.sh server --server-url <url>`, where `<url>` is the server's `/v1` base URL. They check the server's
endpoints, routing, errors and scheduling through the `ai_models` client with the server's tiny models, not the
models' output.

The client settings are tests/server/config.yaml (`SERVER_CONFIG`) with `providers.server.base_url` set to the URL
(`server_config`), in use in this process for the session. Without `--server-url` every test fails with a message
naming the option. The server's config must hold the tiny providers of tests/config.yaml as `test_<provider>`, a
provider of kind `ollama` named `ollama`, and the Ollama models of SERVER_CONFIG pulled (docs/model_server.md,
Tests).

Each test module sets a timeout for network calls (`TIMEOUT_SECONDS`, a video job `VIDEO_TIMEOUT_SECONDS`), above
the default 30 s: the first request to a model loads it on the server."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import options
from tests.settings_env import config_sections, use_settings, write_config

SERVER_CONFIG = Path(__file__).resolve().parent / "config.yaml"
# The client's provider of the model server in SERVER_CONFIG.
SERVER = "server"
# The prefix of the server's provider names of the tiny providers of tests/config.yaml.
TEST = "test_"
# The prefix of the server's Ollama model ids: the name of its provider of kind ollama.
OLLAMA = "ollama:"
TIMEOUT_SECONDS = 180
VIDEO_TIMEOUT_SECONDS = 300
MISSING_URL = ("missing prerequisite: --server-url <url>, the /v1 base URL of the model server under test "
               "(scripts/tests.sh server --server-url http://<host>:<port>/v1)")


def server_config(path: Path, url: str) -> Path:
    """Write at `path` the settings of SERVER_CONFIG with the `base_url` of provider SERVER set to `url`; return
    `path`."""
    sections = config_sections(SERVER_CONFIG)
    sections["providers"][SERVER]["base_url"] = url
    return write_config(path, **sections)


def model(name: str) -> str:
    """The client's model id (`server:<server id>`) of the model of SERVER_CONFIG whose server id ends with
    `:<name>` (`chatterbox-turbo`, `ltx2-tiny`; `gemma3:270m` matches `ollama:gemma3:270m` on its tag)."""
    ids = [m for m in config_sections(SERVER_CONFIG)["providers"][SERVER]["models"]
           if m.split(":", 1)[-1] == name or m == name]
    assert len(ids) == 1, f"tests/server/config.yaml has no single model named {name}: {ids}"
    return f"{SERVER}:{ids[0]}"


def local_models() -> list[str]:
    """The client's model ids of the tiny local models of SERVER_CONFIG (server provider `test_<provider>`)."""
    return [f"{SERVER}:{m}" for m in config_sections(SERVER_CONFIG)["providers"][SERVER]["models"]
            if m.startswith(TEST)]


def ollama_tag(client_id: str) -> str:
    """The Ollama tag of the client's id `server:ollama:<tag>` of an Ollama model of the server."""
    return client_id.removeprefix(f"{SERVER}:").removeprefix(OLLAMA)


def task(name: str) -> str:
    """The client's model id of task `name` in SERVER_CONFIG."""
    return config_sections(SERVER_CONFIG)["tasks"][name]


def server_root() -> str:
    """The server's base URL without `/v1`, for the Ollama paths under `/api/`."""
    url = options.server_url()
    assert url, MISSING_URL
    return url.removesuffix("/v1")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item) -> None:
    """Fail each test of this suite, in its call, when `--server-url` is not given."""
    if options.server_url() is None:
        raise AssertionError(MISSING_URL)


@pytest.fixture(scope="session", autouse=True)
def client_settings(tmp_path_factory) -> Iterator[Path | None]:
    """The settings of `server_config` at the `--server-url` URL, in use for the session; None without the option,
    whose absence fails each test (`pytest_runtest_call`)."""
    url = options.server_url()
    if url is None:
        yield None
        return
    with use_settings(server_config(tmp_path_factory.mktemp("server") / "config.yaml", url)) as path:
        yield path
