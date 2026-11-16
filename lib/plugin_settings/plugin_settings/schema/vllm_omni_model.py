"""`providers.<p>.models.<m>` of a vllm-omni provider: one speech model a vLLM-Omni server serves."""

from __future__ import annotations

from pydantic import PositiveFloat

from .voices import Voices

# GB the server takes outside `memory` when the model has no `overhead` (docs/ai_models.md).
DEFAULT_OVERHEAD_GB = 22.0


class VllmOmniModel(Voices):
    """`repo`: the Hugging Face repository; `deploy`: the deploy config (a file of vLLM-Omni's `deploy/` directory
    or a path); `memory`: GB the server's stages take together; `overhead`: GB it takes outside them; `style`: a
    format string with {instructions} and {text} (None: the model takes no instructions)."""

    repo: str
    deploy: str
    memory: PositiveFloat
    overhead: PositiveFloat = DEFAULT_OVERHEAD_GB
    style: str | None = None
