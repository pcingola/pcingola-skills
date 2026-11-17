"""A first take of a Fish voice: the reference of the later requests of that voice (`fish_takes.Takes`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Take:
    """One answer of the model: `wav` (a WAV file), `text` (what the model got, without the speaker tag) and
    `codes` (the codec codes of the answer, a torch tensor [codebooks, frames] on the CPU)."""

    wav: bytes
    text: str
    codes: Any
