"""`ModelRef`: the `model` field of a request, resolved against the server's config.

A model id is `<provider>:<model>`, split at the first colon. When `<provider>` names a provider of a local kind
(`LOCAL_KINDS`: diffusers, fish, kokoro, chatterbox, torchaudio) in the server's config, the request runs in process
and `<model>` must be an entry of that provider's `models`. When `<provider>` is the Ollama prefix (`ollama_prefix`:
the name of the config's first provider of kind `ollama`, `ollama` when it has none), the request goes to Ollama with
`<model>` as the Ollama tag: `ollama:gemma3:270m` is the tag `gemma3:270m`. Any other id, a bare Ollama tag
included, is a 404 `model_not_found`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plugin_settings import LOCAL_KINDS, Config, ProviderKind

from .model_role import ModelRole
from .route import Route
from .server_error import ErrorType, ServerError

# The Ollama prefix of a config without a provider of kind `ollama`.
OLLAMA_PREFIX = "ollama"
# The in-process kinds whose calls run in parallel threads: the torchaudio aligner holds no state between calls.
# Diffusers pipelines, Fish, Kokoro (espeak-ng) and Chatterbox (one conditioned voice) run one call at a time.
PARALLEL_KINDS = frozenset({ProviderKind.TORCHAUDIO})
# The kinds whose models load to the GPU (CUDA or MPS); the others run on the CPU.
GPU_KINDS = frozenset({ProviderKind.DIFFUSERS, ProviderKind.FISH})
GB = 1e9


def ollama_prefix(cfg: Config) -> str:
    """The prefix of the Ollama model ids of the server of `cfg` (module docstring)."""
    return next((name for name, spec in cfg.providers.items() if spec.kind == ProviderKind.OLLAMA), OLLAMA_PREFIX)


def not_found(model: str, message: str) -> ServerError:
    """The 404 `model_not_found` of `model`, with `message` saying why."""
    return ServerError(404, f"the model {model!r} does not exist: {message}", ErrorType.NOT_FOUND, "model_not_found",
                       "model")


@dataclass(frozen=True)
class ModelRef:
    """A request's model: its id as the request names it, its route, the provider name (the Ollama prefix for an
    Ollama model) and the model name (the Ollama tag); for a local model also its kind, config entry, role and
    whether its provider marks it a test model (`test`)."""

    id: str
    route: Route
    provider: str | None = None
    kind: ProviderKind | None = None
    name: str | None = None
    entry: Any = None
    role: ModelRole | None = None
    test: bool = False

    @classmethod
    def parse(cls, model: object, cfg: Config) -> ModelRef:
        """The `ModelRef` of `model` (module docstring); `ServerError` 400 when it is not a non-empty string, 404
        when it names no local model and no Ollama model."""
        if not isinstance(model, str) or not model.strip():
            raise ServerError(400, "the request names no model (`model`)", param="model")
        name, sep, bare = model.partition(":")
        spec = cfg.provider(name) if sep else None
        if spec is not None and spec.kind in LOCAL_KINDS:
            entry = spec.models.get(bare)
            if entry is None:
                raise not_found(model, f"provider {name!r} has no model {bare!r}")
            return cls(model, Route.LOCAL, name, ProviderKind(spec.kind), bare, entry, ModelRole.of(spec.kind, entry),
                       spec.test)
        prefix = ollama_prefix(cfg)
        if name == prefix and bare:
            return cls(model, Route.OLLAMA, prefix, name=bare)
        raise not_found(model, f"a local model is <provider>:<model> of a local provider of the server, and an "
                         f"Ollama model is {prefix}:<tag> ({prefix}:{model} for the Ollama tag {model})")

    @property
    def local(self) -> bool:
        return self.route == Route.LOCAL

    @property
    def tag(self) -> str | None:
        """The Ollama tag of an Ollama model, None for a local model."""
        return None if self.local else self.name

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
