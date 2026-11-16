"""Image generation and edits with reference images: Pydantic-AI's `ImageGenerator`.

    google                          GoogleImageGenerationModel
    ollama, openrouter, openai,     OpenAIImageGenerationModel (`images/generations`,
    azure                           `images/edits` with reference images)
    diffusers                       `local.DiffusersImageModel`

A `mask` (PNG, the size of the first reference image; transparent pixels mark
the area to repaint) goes to `MaskedOpenAIImageModel` on the OpenAI kinds, and
to the inpaint pipeline of a `diffusers` model.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from pydantic_ai.exceptions import UserError
from plugin_settings import OPENAI_KINDS, ProviderKind
from pydantic_ai.images.openai import OpenAIImageGenerationModel

from . import config
from .errors import ConfigError
from .models import provider



class _MaskedClient:
    """An `AsyncOpenAI` client whose `images.edit` sends `mask`."""

    def __init__(self, client: Any, mask: bytes) -> None:
        self._client = client
        self.images = type("Images", (), {})()
        self.images.edit = partial(client.images.edit, mask=("mask.png", mask, "image/png"))
        self.images.generate = client.images.generate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class MaskedOpenAIImageModel(OpenAIImageGenerationModel):
    """`OpenAIImageGenerationModel` that sends a mask with every edit; it needs a reference image."""

    def __init__(self, model_name: str, *, mask: bytes, **kwargs: Any) -> None:
        super().__init__(model_name, **kwargs)
        self.mask = mask

    @property
    def _client(self) -> Any:
        return _MaskedClient(self._provider.client, self.mask)

    async def generate(self, prompt: str, *, images=None, settings=None):
        if not images:
            raise UserError("a mask needs a reference image to edit")
        return await super().generate(prompt, images=images, settings=settings)


def image_model(model: str | None = None, *, task: str = "image", mask: bytes | None = None):
    """The Pydantic-AI image generation model of `model` (a model id), else of `task`."""
    model_id = config.resolve(model, task)
    name, bare = config.split_id(model_id)
    kind = config.provider(name).kind
    if kind == ProviderKind.DIFFUSERS:
        from .local import DiffusersImageModel

        return DiffusersImageModel(model_id, mask=mask)
    if kind in OPENAI_KINDS:
        if mask is not None:
            return MaskedOpenAIImageModel(bare, mask=mask, provider=provider(name))
        return OpenAIImageGenerationModel(bare, provider=provider(name))
    if mask is not None:
        raise ConfigError(f"provider {name!r} of kind {kind!r} takes no mask")
    if kind == ProviderKind.GOOGLE:
        from pydantic_ai.images.google import GoogleImageGenerationModel

        return GoogleImageGenerationModel(bare, provider=provider(name))
    raise ConfigError(f"provider {name!r} of kind {kind!r} has no image models")


def image_generator(model: str | None = None, *, task: str = "image", mask: bytes | None = None, **kwargs: Any):
    """An `ImageGenerator` on `image_model`; `kwargs` (such as `settings`) go to `ImageGenerator`."""
    from pydantic_ai.images import ImageGenerator

    return ImageGenerator(image_model(model, task=task, mask=mask), **kwargs)
