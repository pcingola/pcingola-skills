"""Script parsing: one sentence per line, blank lines skipped.

No further sentence splitting: the caller decides sentence boundaries, and
`timing.json` indexes exactly those lines. A line may start with its own
style in square brackets, `[whisper] Keep it quiet.`: `split_style` takes it
off the sentence, which is spoken with that style instead of `--style`.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE_RE = re.compile(r"^\[([^\[\]]+)\]\s*(\S.*)$")


def parse_script(text: str) -> list[str]:
    return [s for s in (line.strip() for line in text.splitlines()) if s]


def read_script(path: str | Path) -> list[str]:
    return parse_script(Path(path).read_text(encoding="utf-8"))


def split_style(line: str) -> tuple[str | None, str]:
    """(the line's own style, the sentence): `[style] sentence` gives the style, any other line None."""
    m = STYLE_RE.match(line)
    return (" ".join(m.group(1).split()), m.group(2)) if m else (None, line)
