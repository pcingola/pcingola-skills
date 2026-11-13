"""Numbered version directories (`v1`, `v2`, ...) that are never reused.

The highest number ever issued is recorded in `<dir>/.last_version`, so a
number is not handed out again even after its directory (including the
newest one) is deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_RE = re.compile(r"^v(\d+)$")
_COUNTER = ".last_version"


def version_number(path: Path) -> int | None:
    m = _VERSION_RE.match(path.name)
    return int(m.group(1)) if m else None


def list_versions(parent: Path) -> list[Path]:
    """Existing version directories under `parent`, oldest first."""
    if not parent.is_dir():
        return []
    found = [(version_number(p), p) for p in parent.iterdir() if p.is_dir()]
    return [p for n, p in sorted((n, p) for n, p in found if n is not None)]


def _last_issued(parent: Path) -> int:
    try:
        return int((parent / _COUNTER).read_text().strip())
    except (OSError, ValueError):
        return 0


def next_version(parent: Path) -> Path:
    """Create and return `parent/v<N>` with N one above any number ever issued."""
    parent.mkdir(parents=True, exist_ok=True)
    existing = [version_number(p) or 0 for p in list_versions(parent)]
    n = max([_last_issued(parent), *existing]) + 1
    path = parent / f"v{n}"
    path.mkdir(exist_ok=False)
    (parent / _COUNTER).write_text(f"{n}\n")
    return path


def latest_version(parent: Path, require: str | None = None) -> Path | None:
    """Highest existing version directory, optionally only those containing `require`."""
    for p in reversed(list_versions(parent)):
        if require is None or (p / require).exists():
            return p
    return None
