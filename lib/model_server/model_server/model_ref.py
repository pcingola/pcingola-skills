"""`ModelRef`: the `model` field of a request, resolved against the server's config.

A model id is `<provider>:<model>`, split at the first colon. When `<provider>` names a provider of a local kind
(`LOCAL_KINDS`: diffusers, fish, kokoro, chatterbox, torchaudio) in the server's config, the request runs in process
and `<model>` must be an entry of that provider's `models`. Any other id goes to Ollama unchanged, so an Ollama tag
such as `gemma3:270m` is written as it is. A local provider's name therefore hides the Ollama models whose name
before the colon is the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plugin_settings import LOCAL_KINDS, Config, ProviderKind

from .model_role import ModelRole
from .route import Route
from .server_error import ErrorType, ServerError

# The in-process kinds whose calls run in parallel threads: the torchaudio aligner holds no state between calls.
# Diffusers pipelines, Fish, Kokoro (espeak-ng) and Chatterbox (one conditioned voice) run one call at a time.
PARALLEL_KINDS = frozenset({ProviderKind.TORCHAUDIO})
# The kinds whose models load to the GPU (CUDA or MPS); the others run on the CPU.
GPU_KINDS = frozenset({ProviderKind.DIFFUSERS, ProviderKind.FISH})
GB = 1e9


@dataclass(frozen=True)
class ModelRef:
    """A request's model: its id as the request names it, its route and, for a local model, the provider name,
    kind, model name, config entry and role."""

    id: str
    route: Route
    provider: str | None = None
    kind: ProviderKind | None = None
    name: str | None = None
    entry: Any = None
    role: ModelRole | None = None

    @classmethod
    def parse(cls, model: object, cfg: Config) -> ModelRef:
        """The `ModelRef` of `model` (module docstring); `ServerError` 400 when it is not a non-empty string, 404
        when its provider is local and has no such model."""
        if not isinstance(model, str) or not model.strip():
            raise ServerError(400, "the request names no model (`model`)", param="model")
        name, sep, bare = model.partition(":")
        spec = cfg.provider(name) if sep else None
        if spec is None or spec.kind not in LOCAL_KINDS:
            return cls(model, Route.OLLAMA)
        entry = spec.models.get(bare)
        if entry is None:
            raise ServerError(404, f"the model {model!r} does not exist: provider {name!r} has no model {bare!r}",
                              ErrorType.NOT_FOUND, "model_not_found", "model")
        return cls(model, Route.LOCAL, name, ProviderKind(spec.kind), bare, entry, ModelRole.of(spec.kind, entry))

    @property
    def local(self) -> bool:
        return self.route == Route.LOCAL

    @property
    def parallel(self) -> bool:
        """True when several requests to this model run at once: Ollama's models and the `PARALLEL_KINDS`."""
        return not self.local or self.kind in PARALLEL_KINDS

    @property
    def gpu(self) -> bool:
        """True for a local model of a kind that loads to the GPU (`GPU_KINDS`)."""
        return self.kind in GPU_KINDS

    @property
    def memory(self) -> int | None:
        """The bytes the local model takes at its peak (its entry's `memory`), None when unset or not local."""
        gb = getattr(self.entry, "memory", None)
        return None if gb is None else int(gb * GB)

    def require(self, *roles: ModelRole) -> ModelRef:
        """This ref when it is a local model of one of `roles`; `ServerError` 400 otherwise."""
        if self.role not in roles:
            what = f"a local {self.role} model" if self.local else "not a model of a local provider of the server"
            raise ServerError(400, f"{self.id} is {what}; this endpoint takes a local "
                              + " or ".join(r.value for r in roles) + " model", param="model",
                              code="model_not_supported")
        return self
