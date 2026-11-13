"""Brand: an optional logo beside the creator caption.

`brand:` in the settings names the brand (e.g. acme). Its folder is the
one the brand skill reports for that name, passed as `--brand DIR` and read in
place; the folder's name must be the `brand:` value. The folder holds
`brand.yaml` (the video caption keys `raster`, the optional `raster_on_dark`
and `caption`, and `logo`), the
logo files and `guidelines.md`, the rules for placing the logo in a film.
Nothing here knows about a particular brand.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import yaml

BRAND_FILE = "brand.yaml"


def _no_folder(name: str) -> str:
    return (f"brand {name!r} is set in the settings: get the folder of brand {name} from the brand skill "
            f"(`brand:brand`) and pass it as --brand")


def _absolute(folder: Path | str) -> Path:
    """`folder` as an absolute path, without following symlinks, so a
    symlinked folder keeps its own name (`.` names the current dir)."""
    return Path(os.path.abspath(Path(folder).expanduser()))


def load(name: str | None, folder: Path | str | None = None) -> dict | None:
    """`brand.yaml` of the brand folder `folder` with `dir` added; None when no
    brand `name` is set. Raises ValueError when the folder is missing, is not
    named `name`, has no brand.yaml, or lacks its caption logo or ratios."""
    if not name:
        return None
    if folder is None:
        raise ValueError(_no_folder(name))
    d = _absolute(folder)
    _require_brand_file(d)
    if d.name != name:
        raise ValueError(f"--brand {d} is the folder of brand {d.name!r}, "
                         f"but the settings name brand {name!r}")
    return load_dir(d, name)


def resolve(arg: Path | str) -> dict:
    """The brand in folder `arg` (one with brand.yaml, as the brand skill
    reports it), named after the folder. Raises ValueError."""
    d = _absolute(arg)
    _require_brand_file(d)
    return load_dir(d, d.name)


def _require_brand_file(d: Path) -> None:
    if not (d / BRAND_FILE).is_file():
        raise ValueError(f"brand folder {d}: no {BRAND_FILE} in it")


def load_dir(d: Path, name: str) -> dict:
    """`brand.yaml` of the brand folder `d` with `dir` added. Raises ValueError
    when its caption logo or its caption ratios are missing, or when
    `raster_on_dark` (optional) is not a PNG with the aspect ratio of `raster`."""
    with (d / BRAND_FILE).open(encoding="utf-8") as f:
        b = yaml.safe_load(f) or {}
    if not isinstance(b, dict):
        raise ValueError(f"brand {name!r}: {d / BRAND_FILE} must be a mapping")
    b["dir"] = d
    raster = _png(b, d, name, "raster")
    if b.get("raster_on_dark") is not None:
        on_dark = _png(b, d, name, "raster_on_dark")
        (w, h), (w2, h2) = png_size(raster), png_size(on_dark)
        # Same box at any logo height: the widths agree within 1 px at the larger height.
        if abs(w * h2 - w2 * h) > max(h, h2):
            raise ValueError(f"brand {name!r}: `raster_on_dark:` {on_dark.name} ({w2}x{h2}) must have the "
                             f"aspect ratio of `raster:` {raster.name} ({w}x{h}) in {d / BRAND_FILE}")
    cap = b.get("caption")
    if not isinstance(cap, dict) or not all(isinstance(cap.get(k), (int, float)) for k in ("height", "gap")):
        raise ValueError(f"brand {name!r}: `caption:` in {d / BRAND_FILE} needs numeric `height` and `gap`")
    return b


def _png(b: dict, d: Path, name: str, key: str) -> Path:
    """The PNG file named by `key` in the brand folder `d`. Raises ValueError."""
    path = d / str(b.get(key) or "")
    if not b.get(key) or path.suffix.lower() != ".png" or not path.is_file():
        raise ValueError(f"brand {name!r}: `{key}:` in {d / BRAND_FILE} must name a PNG file in that folder")
    return path


def problems(name: str | None, folder: Path | str | None = None) -> list[str]:
    """What `validate` reports about the brand: missing folder or files."""
    if not name:
        return [f"--brand {folder} is given but no `brand:` is set in the settings; `assemble` refuses it"] \
            if folder else []
    if folder is None:
        return [f"{_no_folder(name)}; `assemble` refuses to run without it"]
    try:
        b = load(name, folder)
    except ValueError as e:
        return [str(e)]
    out = []
    logo = b["dir"] / str(b.get("logo", ""))
    if not b.get("logo") or not logo.is_file():
        out.append(f"brand {name!r}: `logo:` in {b['dir'] / BRAND_FILE} must name a file in that folder")
    elif logo.suffix.lower() not in (".svg", ".png"):
        out.append(f"brand {name!r}: the logo {logo.name} is not an SVG or PNG")
    return out


def png_size(path: Path) -> tuple[int, int]:
    """(width, height) of a PNG from its header."""
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])
