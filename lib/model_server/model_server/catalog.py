"""The models of the server as `openai.types.Model` objects (`GET /v1/models`).

A local model's object is `id` (`<provider>:<model>`), `object: "model"`, `created: 0`, `owned_by` (the provider
name) and four more fields: `kind` (the provider kind), `role` (`ModelRole`: image, music, video, presenter, speech,
align), `test` (the provider's `test`: a test model) and `entry` (the model's entry of the config, every key with its
value or default, as JSON). A client reads the
attributes it needs from `entry`: a video model's `fps`, `frame_step`, `max_frames`, `width`, `height` and
`size_multiple`, a presenter's `buckets`, an image model's `image` limits, a music model's `min_crest_db`. The
object of one speech model (`GET /v1/models/{id}`) also has `voices`, the list `ai_models.speech.voices` gives.

An Ollama model's object is Ollama's (`ollama_object`) with `id` the server's id (`<prefix>:<tag>`), `kind:
"ollama"` and its `role` (chat or embedding) when Ollama gives it.
"""

from __future__ import annotations

from typing import Any

from openai.types import Model
from plugin_settings import LOCAL_KINDS, Config, ProviderKind

from .model_ref import ModelRef
from .model_role import ModelRole


def model_object(ref: ModelRef, voices: list[str] | None = None) -> Model:
    """The `Model` of the local model `ref`, with `voices` when given."""
    more = {} if voices is None else {"voices": voices}
    return Model(id=ref.id, object="model", created=0, owned_by=ref.provider, kind=ref.kind.value,
                 role=ref.role.value, test=ref.test, entry=ref.entry.model_dump(mode="json"), **more)


def local_models(cfg: Config) -> list[Model]:
    """The `Model` of every model of every provider of a local kind in `cfg`, in config order."""
    return [model_object(ModelRef.parse(f"{name}:{model}", cfg)) for name, spec in cfg.providers.items()
            if spec.kind in LOCAL_KINDS for model in spec.models]


def ollama_object(data: dict[str, Any], model_id: str, role: ModelRole | None) -> dict[str, Any]:
    """Ollama's object of a model (`data`) with `id` `model_id`, `kind` ollama and `role` when not None."""
    more = {} if role is None else {"role": role.value}
    return {**data, "id": model_id, "kind": ProviderKind.OLLAMA.value, **more}
