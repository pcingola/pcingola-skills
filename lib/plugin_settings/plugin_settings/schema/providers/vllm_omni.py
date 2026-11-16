"""A provider of kind vllm-omni: one speech model (`repo`) served by vLLM-Omni from its own environment (`python`).
`deploy`: the deploy config; `memory`: GB the server's stages take together; `overhead`: GB it takes outside them;
`style`: format string with {instructions} and {text}; `args`: more server arguments; `env`: server environment
variables; `start_timeout`: seconds the start may take."""

from __future__ import annotations

from typing import Literal

from pydantic import PositiveFloat

from ..fields import UserPath
from .base import TimedProvider

# GB the server takes outside `memory` when the provider has no `overhead` (docs/ai_models.md).
DEFAULT_OVERHEAD_GB = 22.0
DEFAULT_START_TIMEOUT = 1800.0


class VllmOmniProvider(TimedProvider):
    kind: Literal["vllm-omni"]
    python: UserPath
    repo: str
    deploy: str
    memory: PositiveFloat
    overhead: PositiveFloat = DEFAULT_OVERHEAD_GB
    style: str | None = None
    args: list[str | int | float] = []
    env: dict[str, str | int | float] = {}
    start_timeout: PositiveFloat = DEFAULT_START_TIMEOUT
    voice: str | None = None
    voices: list[str] | None = None
