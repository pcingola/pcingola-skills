"""Script parsing: one sentence per line, blank lines skipped.

No further sentence splitting: the caller decides sentence boundaries, and `timing.json` indexes exactly those
lines. `Line.of` reads what a line holds besides its text, as far as the model takes it:

- A model that takes inline tags (vllm-omni, Fish Audio Drama 3): a line may start with `@<speaker> ` (a name of
  lowercase letters, digits, `-`, `_`), which says who speaks it; the rest of the line goes to the model as written,
  with its tags in square brackets (`[laughs]`, `[whisper]`) and speaker tags (`<|speaker:1|>`) anywhere in it.
  The sentence the aligner and `timing.json` see is the line without those tags (`strip_tags`).
- A model that takes a style but no inline tags: a line may start with its own style in square brackets,
  `[whisper] Keep it quiet.`; `split_style` takes it off the sentence, which is spoken with that style instead of
  `--style`.
- Any other model: the line is literal text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STYLE_RE = re.compile(r"^\[([^\[\]]+)\]\s*(\S.*)$")
SPEAKER_RE = re.compile(r"^@([a-z0-9][a-z0-9_-]*)\s+(\S.*)$")
TAG_RE = re.compile(r"\[[^\[\]]*\]|<\|[^|]*\|>")


def parse_script(text: str) -> list[str]:
    return [s for s in (line.strip() for line in text.splitlines()) if s]


def read_script(path: str | Path) -> list[str]:
    return parse_script(Path(path).read_text(encoding="utf-8"))


def split_style(line: str) -> tuple[str | None, str]:
    """(the line's own style, the sentence): `[style] sentence` gives the style, any other line None."""
    m = STYLE_RE.match(line)
    return (" ".join(m.group(1).split()), m.group(2)) if m else (None, line)


def split_speaker(line: str) -> tuple[str | None, str]:
    """(speaker, the rest): `@name text` gives the speaker, any other line None."""
    m = SPEAKER_RE.match(line)
    return (m.group(1), m.group(2)) if m else (None, line)


def strip_tags(text: str) -> str:
    """`text` without its bracket tags and speaker tags, spaces collapsed."""
    return " ".join(TAG_RE.sub(" ", text).split())


@dataclass(frozen=True)
class Line:
    """One script line: `text` the sentence (aligned, written to timing.json), `said` what the model gets, `style`
    its own style, `speaker` who speaks it."""

    text: str
    said: str
    style: str | None = None
    speaker: str | None = None

    @classmethod
    def of(cls, line: str, *, styles: bool, tags: bool) -> Line:
        """The line for a model that takes `styles` (instructions) and inline `tags`; `ValueError` for a line of a
        tag model that holds only tags."""
        if tags:
            speaker, said = split_speaker(line)
            text = strip_tags(said)
            if not text:
                raise ValueError(f"script line {line!r} has only tags, no words")
            return cls(text, said, None, speaker)
        if styles:
            style, text = split_style(line)
            return cls(text, text, style)
        return cls(line, line)
