"""The prompt sent to a music model.

Lyria has no request fields for tempo or vocals; `compose` writes them into
the prompt text in a fixed order: tempo, then instrumental. `ai_models.music`
adds the length and the lyrics block for Lyria 3.

A local `diffusers` model (ACE-Step) takes the prompt as style tags; the
tempo is a tag (`tags`), and no vocals is the lyrics `[instrumental]`
(`local_lyrics`).
"""

from __future__ import annotations


def compose(prompt: str, instrumental: bool = False, bpm: int | None = None) -> str:
    parts = [prompt.strip()]
    if parts[0] and parts[0][-1] not in ".!?":
        parts[0] += "."
    if bpm:
        parts.append(f"Tempo: {bpm} BPM.")
    if instrumental:
        parts.append("Instrumental only, no vocals.")
    return " ".join(p for p in parts if p)


INSTRUMENTAL = "[instrumental]"


def tags(prompt: str, bpm: int | None = None) -> str:
    """The ACE-Step prompt: `prompt` with the tempo appended as a tag (`, 90 bpm`)."""
    text = prompt.strip()
    if bpm:
        text = f"{text.rstrip('.,')}, {bpm} bpm" if text else f"{bpm} bpm"
    return text


def local_lyrics(lyrics: str | None, instrumental: bool = False) -> str | None:
    """The ACE-Step lyrics: `[instrumental]`, the lyrics, or None (the pipeline's default)."""
    if lyrics and instrumental:
        raise ValueError("lyrics and instrumental are mutually exclusive")
    if instrumental:
        return INSTRUMENTAL
    return lyrics.strip() if lyrics and lyrics.strip() else None
