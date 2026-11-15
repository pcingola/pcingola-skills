"""The prompt sent to a music model.

A remote (Google) music model has no request fields for tempo or vocals;
`compose` writes them into the prompt text in a fixed order: tempo, then
instrumental. Neither kind gets the tempo added when the prompt already
names it (`names_tempo`). `ai_models.music` adds the length and the lyrics block.

A local `diffusers` model takes the prompt as style tags; the
tempo is a tag (`tags`), and no vocals is the lyrics `[instrumental]`
(`local_lyrics`).

`request` picks the prompt and the lyrics sent for the model's kind; sung
lyrics reach both kinds.
"""

from __future__ import annotations

import re


def names_tempo(prompt: str, bpm: int) -> bool:
    """Whether `prompt` names the tempo `bpm` (`90 bpm`, `90 BPM`, `90bpm`); the tempo is then not added again."""
    return re.search(rf"(?<!\d){bpm}\s*bpm\b", prompt, re.IGNORECASE) is not None


def compose(prompt: str, instrumental: bool = False, bpm: int | None = None) -> str:
    parts = [prompt.strip()]
    if parts[0] and parts[0][-1] not in ".!?":
        parts[0] += "."
    if bpm and not names_tempo(parts[0], bpm):
        parts.append(f"Tempo: {bpm} BPM.")
    if instrumental:
        parts.append("Instrumental only, no vocals.")
    return " ".join(p for p in parts if p)


INSTRUMENTAL = "[instrumental]"


def tags(prompt: str, bpm: int | None = None) -> str:
    """The local model prompt: `prompt` with the tempo appended as a tag (`, 90 bpm`), unless the prompt already
    names that tempo (`names_tempo`)."""
    text = prompt.strip()
    if bpm and not names_tempo(text, bpm):
        text = f"{text.rstrip('.,')}, {bpm} bpm" if text else f"{bpm} bpm"
    return text


def local_lyrics(lyrics: str | None, instrumental: bool = False) -> str | None:
    """The local model lyrics: `[instrumental]`, the lyrics, or None (the pipeline's default)."""
    if lyrics and instrumental:
        raise ValueError("lyrics and instrumental are mutually exclusive")
    if instrumental:
        return INSTRUMENTAL
    return lyrics.strip() if lyrics and lyrics.strip() else None


def request(prompt: str, lyrics: str | None, instrumental: bool, bpm: int | None, local: bool) -> tuple[str, str | None]:
    """(prompt, lyrics) sent to `ai_models.music.compose`: a local model gets
    `tags` and `local_lyrics`, a remote model gets `compose` and the lyrics as given."""
    if local:
        return tags(prompt, bpm), local_lyrics(lyrics, instrumental)
    if lyrics and instrumental:
        raise ValueError("lyrics and instrumental are mutually exclusive")
    return compose(prompt, instrumental, bpm), lyrics or None
