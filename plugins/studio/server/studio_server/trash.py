"""Moving a project directory to the user's Trash, with the standard library only."""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def _free(directory: Path, name: str) -> Path:
    """`directory/name`, else `name 2`, `name 3`, ...: the first that does not exist."""
    p, n = directory / name, 1
    while p.exists() or p.is_symlink():
        n += 1
        p = directory / f"{name} {n}"
    return p


def trash_dir() -> Path:
    """The Trash: `~/.Trash` on macOS, the freedesktop.org trash on Linux (`$XDG_DATA_HOME/Trash`, by default
    `~/.local/share/Trash`), `~/.studio-trash` elsewhere (Windows has no Recycle Bin call in the standard library)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / ".Trash"
    if sys.platform.startswith("linux"):
        return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "Trash"
    return home / ".studio-trash"


def move_to_trash(path: Path, label: str, root: Path | None = None) -> Path:
    """Moves the directory `path` into the Trash `root` (None: trash_dir()) as `label` (`label 2`, ... when taken);
    on Linux into `files/` with its `info/<name>.trashinfo`, so the desktop's Trash can restore it. Answers the new
    path."""
    root = root or trash_dir()
    linux = sys.platform.startswith("linux")
    files = root / "files" if linux else root
    files.mkdir(parents=True, exist_ok=True)
    target = _free(files, label)
    if linux:
        info = root / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / f"{target.name}.trashinfo").write_text(
            f"[Trash Info]\nPath={quote(str(path))}\nDeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n",
            encoding="utf-8")
    shutil.move(str(path), str(target))
    return target
