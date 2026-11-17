"""`built`: the folder of a tiny random-weight model, written by its builder when missing."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path


def built(folder: Path, build: Callable[[Path], Path]) -> Path:
    """`folder`, written with `build(tmp)` when missing. `build` writes into a temporary folder beside it, which is
    then renamed, so an interrupted build leaves no partial folder."""
    if not folder.is_dir():
        folder.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"{folder.name}-", dir=folder.parent))
        try:
            build(tmp).rename(folder)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return folder
