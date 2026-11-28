"""The field every provider of a local kind has: `test`."""

from __future__ import annotations

from ..base import Strict


class LocalProvider(Strict):
    """A provider of a local kind (diffusers, fish, kokoro, chatterbox, torchaudio). `test: true` marks its models
    as test models: a model server lists them with `test: true`, and `model-client models` shows them only with
    `--tests`."""

    test: bool = False
