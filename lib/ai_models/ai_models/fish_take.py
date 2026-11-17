"""A first take of a Fish voice: the reference of the later requests of that voice (`fish_takes.Takes`).

A take saved to a folder (`Take.save`) is three files: `voice.wav` (the audio), `voice.txt` (the styled text the
model got) and `codes.pt` (the codec codes, `torch.save` of a CPU tensor). `Take.load` reads them back, so a later
process can seed `fish.takes` with the voice of an earlier one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AIModelsError

WAV_FILE = "voice.wav"
TEXT_FILE = "voice.txt"
CODES_FILE = "codes.pt"


@dataclass(frozen=True)
class Take:
    """One answer of the model: `wav` (a WAV file), `text` (what the model got, without the speaker tag) and
    `codes` (the codec codes of the answer, a torch tensor [codebooks, frames] on the CPU)."""

    wav: bytes
    text: str
    codes: Any

    def save(self, folder: str | Path) -> Path:
        """Write the take to `folder` (created when missing) as `WAV_FILE`, `TEXT_FILE` and `CODES_FILE`; the
        folder."""
        import torch

        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / WAV_FILE).write_bytes(self.wav)
        (folder / TEXT_FILE).write_text(self.text, encoding="utf-8")
        torch.save(self.codes, folder / CODES_FILE)
        return folder

    @classmethod
    def load(cls, folder: str | Path) -> Take:
        """The take saved in `folder` by `save`; `AIModelsError` naming the missing file when one is absent."""
        import torch

        folder = Path(folder)
        if missing := [n for n in (WAV_FILE, TEXT_FILE, CODES_FILE) if not (folder / n).is_file()]:
            raise AIModelsError(f"{folder}: not a saved Fish voice (no {', '.join(missing)})")
        codes = torch.load(folder / CODES_FILE, map_location="cpu", weights_only=True)
        return cls((folder / WAV_FILE).read_bytes(), (folder / TEXT_FILE).read_text(encoding="utf-8"), codes)
