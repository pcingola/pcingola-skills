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

import math
import re
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


# `init --length S` accepts this fraction of S either side before `validate` warns about the length.
LENGTH_TOLERANCE = 0.1


def set_length(path: Path, seconds: float) -> None:
    """Set `length.min_seconds` and `length.max_seconds` in the settings file `path` (a copy of
    `assets/settings.yaml`) to `seconds` less and more `LENGTH_TOLERANCE`, keeping its comments."""
    text = path.read_text(encoding="utf-8")
    for key, value in (("min_seconds", math.floor(seconds * (1 - LENGTH_TOLERANCE))),
                       ("max_seconds", math.ceil(seconds * (1 + LENGTH_TOLERANCE)))):
        text, n = re.subn(rf"^(  {key}:) .*$", rf"\g<1> {value}", text, count=1, flags=re.M)
        if n != 1:
            raise ValueError(f"{path}: no `length.{key}` line")
    path.write_text(text, encoding="utf-8")
    _load.cache_clear()


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


def critic_model() -> str | None:
    """The film critic's model: `critic.model` of the settings, else task `film_critic` of the ai_models config;
    None when `critic.model` is null (the critic is off). Raises ai_models' AIModelsError when neither names a
    model."""
    c = get().get("critic") or {}
    if "model" in c and c["model"] is None:
        return None
    from ai_models import config as ai_config

    return ai_config.resolve(c.get("model"), "film_critic")


def asset(name: str) -> str:
    """Text of a file under `assets/`."""
    return (ASSETS_DIR / name).read_text(encoding="utf-8")
