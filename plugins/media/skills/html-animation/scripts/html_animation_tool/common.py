"""Helpers shared by the commands: paths, the data directory, JSON files and the error type."""
from __future__ import annotations

import json
from pathlib import Path

from plugin_settings import Plugin

SKILL_DIR = Path(__file__).resolve().parents[2]
PLAYER = SKILL_DIR / "assets" / "player.js"


class HAError(Exception):
    """An error reported on stderr with exit status 1."""


def data_dir() -> Path:
    """`<plugin data dir>/html-animation`: pinned libraries and the Chromium install."""
    return Plugin.of(__file__).data_dir() / "html-animation"


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HAError(f"{path} not found") from None
    except json.JSONDecodeError as e:
        raise HAError(f"{path} is not valid JSON: {e}") from None


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
