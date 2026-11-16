"""`huggingface:`: the weights cache of the diffusers models (HF_HOME) and the token for gated repositories."""

from __future__ import annotations

from .base import Strict
from .fields import Secret, UserPath


class HuggingFace(Strict):
    home: UserPath | None = None
    token: Secret | None = None
