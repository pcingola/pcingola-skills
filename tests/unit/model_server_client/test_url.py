"""`model_client.client.server_url` (docs/model_server.md, Command-line client): the server URL from `--url`,
`--provider`, `model_client.provider` and `model_server.port`, in that order, read from a real config.yaml with
`use_settings`; a `--provider` that is not a model server's provider is a `ClientError`."""

import pytest

from model_client import client as cli
from tests.settings_env import use_settings, write_config

SERVER = "http://model-server.example.com:8000/v1"
OTHER = "http://other.example.com:9000/v1"
PROVIDERS = {"server": {"kind": "openai", "base_url": SERVER}, "other": {"kind": "openai", "base_url": OTHER},
             "api": {"kind": "openai", "api_key": "k"}, "o": {"kind": "ollama"}}


def test_url_order(tmp_path):
    """`--url` wins over `--provider`, `--provider` over `model_client.provider`, which wins over localhost at
    `model_server.port`; with neither setting, localhost at the default port 8000."""
    file = write_config(tmp_path / "with.yaml", providers=PROVIDERS, model_client={"provider": "server"},
                        model_server={"port": 8123})
    with use_settings(file):
        assert cli.server_url("http://given.example.com/v1", "other") == "http://given.example.com/v1"
        assert cli.server_url(None, "other") == OTHER
        assert cli.server_url() == SERVER
    with use_settings(write_config(tmp_path / "port.yaml", model_server={"port": 8123})):
        assert cli.server_url() == "http://localhost:8123/v1"
    with use_settings(write_config(tmp_path / "empty.yaml")):
        assert cli.server_url() == "http://localhost:8000/v1"


def test_provider_must_be_a_server(tmp_path):
    """A `--provider` that is missing, not of kind `openai` or without a `base_url` is a `ClientError` naming why,
    before any request."""
    with use_settings(write_config(tmp_path / "c.yaml", providers=PROVIDERS)):
        with pytest.raises(cli.ClientError, match="provider 'nope' is not in providers"):
            cli.server_url(None, "nope")
        with pytest.raises(cli.ClientError, match="provider 'o' is of kind ollama"):
            cli.server_url(None, "o")
        with pytest.raises(cli.ClientError, match="provider 'api' has no base_url"):
            cli.server_url(None, "api")
