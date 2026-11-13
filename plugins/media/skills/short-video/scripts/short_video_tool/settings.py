"""Settings and asset files.

Every value the tool uses that is not part of the code's logic (frame size,
encoding, author, voice, music, template rules, credit texts and caption
style, mix levels, player) is in `assets/settings.yaml`. `init`
copies that file into the project as `settings.yaml`; once `use_project` has
named the project, `get()` returns the skill defaults with the project's copy
merged over them (mappings merged key by key, any other value replaced).
Modules call `get()` when they need a value, never at import time, so the
project's copy is the one used. Text the tool writes (default storyboard,
suggested pages, timing helpers, brief text) is in files under `assets/`, read
through `asset()`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# settings.py -> short_video_tool -> scripts -> short-video
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
SETTINGS_FILE = ASSETS_DIR / "settings.yaml"
PROJECT_FILE = "settings.yaml"

_project: Path | None = None


def use_project(project: Path | None) -> None:
    """Read the settings of `project` (its `settings.yaml` over the defaults)
    from now on; None reads the defaults only."""
    global _project
    _project = project
    _load.cache_clear()


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=4)
def _load(project: Path | None) -> dict:
    data = _read(SETTINGS_FILE)
    if project is not None and (project / PROJECT_FILE).is_file():
        data = merge(data, _read(project / PROJECT_FILE))
    return data


def get() -> dict:
    return _load(_project)


def encode() -> dict:
    return get()["encode"]


def authors() -> list[str]:
    """`author:` as a list of names (a single string counts as one name)."""
    a = get().get("author")
    names = [a] if isinstance(a, str) else list(a or [])
    return [n for n in (" ".join(str(x).split()) for x in names) if n]


def author() -> str | None:
    """The author names joined with ", ", or None when there are none."""
    return ", ".join(authors()) or None


def asset(name: str) -> str:
    """Text of a file under `assets/`."""
    return (ASSETS_DIR / name).read_text(encoding="utf-8")
