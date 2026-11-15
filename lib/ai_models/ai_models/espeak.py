"""The espeak-ng data directory for Kokoro (`kokoro`).

kokoro-onnx phonemizes with espeak-ng and passes it the `espeak-ng-data` directory bundled in `espeakng_loader`.
espeak-ng keeps that path in a fixed 160-byte buffer; a longer path is dropped silently and espeak-ng fails with
`Error processing file '.../phontab'`. When the bundled path is `PATH_LIMIT` characters or longer, the data is
copied once to the first short candidate directory and that copy is passed through `EspeakConfig(data_path=...)`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

PATH_LIMIT = 150
MARKER = ".source"
DIR_NAME = "espeak-ng-data"


def candidates(weights_root: Path) -> list[Path]:
    """Short directories for the copy, in order of preference: beside the weights, then the temp directory."""
    return [weights_root / DIR_NAME, Path(tempfile.gettempdir()) / f"ai-models-{DIR_NAME}"]


def choose_data_dir(source: str, dirs: list[Path], limit: int = PATH_LIMIT) -> Path | None:
    """None to use `source` as is, else the first of `dirs` shorter than `limit`."""
    if len(source) < limit:
        return None
    for d in dirs:
        if len(str(d)) < limit:
            return d
    raise RuntimeError(f"espeak-ng data path is too long ({len(source)} characters, limit {limit}) "
                       f"and no short directory is available: {source}")


def ensure_copy(source: Path, dest: Path) -> Path:
    """Copy `source` to `dest` unless `dest` already holds a copy of it."""
    marker = dest / MARKER
    if marker.is_file() and marker.read_text(encoding="utf-8") == str(source):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(source, tmp)
    (tmp / MARKER).write_text(str(source), encoding="utf-8")
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return dest


def data_path(weights_root: Path) -> str:
    """The espeak-ng data directory to pass to kokoro-onnx."""
    import espeakng_loader

    source = espeakng_loader.get_data_path()
    dest = choose_data_dir(source, candidates(weights_root))
    if dest is None:
        return source
    return str(ensure_copy(Path(source), dest))
