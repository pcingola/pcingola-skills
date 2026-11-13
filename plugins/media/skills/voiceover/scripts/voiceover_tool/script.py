"""Script parsing: one sentence per line, blank lines skipped.

No further sentence splitting: the caller decides sentence boundaries, and
`timing.json` indexes exactly those lines.
"""

from __future__ import annotations

from pathlib import Path


def parse_script(text: str) -> list[str]:
    return [s for s in (line.strip() for line in text.splitlines()) if s]


def read_script(path: str | Path) -> list[str]:
    return parse_script(Path(path).read_text(encoding="utf-8"))
