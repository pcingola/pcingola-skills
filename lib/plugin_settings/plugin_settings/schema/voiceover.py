"""`voiceover:`: settings of media:voiceover."""

from __future__ import annotations

from .base import Strict
from .fields import UserPath


class VoiceoverSettings(Strict):
    """`voices_dir`: the reference recordings of `add-voice` and the saved Fish voices (None: the skill's default)."""

    voices_dir: UserPath | None = None
