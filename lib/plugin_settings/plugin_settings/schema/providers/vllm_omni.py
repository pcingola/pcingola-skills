"""A provider of kind vllm-omni: speech models served by a vLLM-Omni server from its own environment (`python`),
one server per model; each model needs an entry in `models`. `args`: more server arguments; `env`: server
environment variables; `start_timeout`: seconds the start may take."""

from __future__ import annotations

from typing import Literal

from pydantic import PositiveFloat

from ..fields import Catalogue
from ..vllm_omni_model import VllmOmniModel
from .own_environment import OwnEnvironment

DEFAULT_START_TIMEOUT = 1800.0


class VllmOmniProvider(OwnEnvironment):
    kind: Literal["vllm-omni"]
    start_timeout: PositiveFloat = DEFAULT_START_TIMEOUT
    args: list[str | int | float] = []
    env: dict[str, str | int | float] = {}
    models: Catalogue[VllmOmniModel] = {}
