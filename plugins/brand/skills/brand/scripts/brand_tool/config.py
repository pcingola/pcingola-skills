"""Settings and brand lookup for the brand CLI.

A brand is a folder `<name>/` holding `brand.yaml`. Search order: the bundled
`brands/` directory of the skill, then each entry of the colon-separated
`BRAND_PATH`, in order. Empty entries and entries that are not directories are
skipped. The first folder named `<name>` with a `brand.yaml` wins.

`BRAND_PATH` is a setting. Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
"""

from __future__ import annotations

from pathlib import Path

from plugin_settings import Plugin

# config.py -> brand_tool -> scripts -> <skill>
BUNDLED_DIR = Path(__file__).resolve().parents[2] / "brands"
BRAND_FILE = "brand.yaml"

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load


class BrandError(Exception):
    """A lookup or copy failure, reported on stderr with exit status 1."""


def search_dirs(bundled: Path | None = None) -> list[Path]:
    """Directories searched for brands, in order, without duplicates.

    The bundled directory first (if it exists), then each `BRAND_PATH` entry
    that is a directory. `~` in an entry is expanded.
    """
    candidates = [bundled if bundled is not None else BUNDLED_DIR]
    for entry in PLUGIN.get("BRAND_PATH", "").split(":"):
        entry = entry.strip()
        if entry:
            candidates.append(Path(entry).expanduser())
    dirs: list[Path] = []
    seen: set[Path] = set()
    for d in candidates:
        if not d.is_dir():
            continue
        key = d.resolve()
        if key in seen:
            continue
        seen.add(key)
        dirs.append(d)
    return dirs


def searched(dirs: list[Path]) -> str:
    return ", ".join(str(d) for d in dirs) if dirs else "(no existing directory)"


def check_name(name: str) -> None:
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise BrandError(f"invalid brand name: {name!r}")


def _is_brand(folder: Path) -> bool:
    try:
        return (folder / BRAND_FILE).is_file()
    except OSError:
        return False


def find(name: str, bundled: Path | None = None) -> Path:
    """The folder of brand `name`: the first `<dir>/<name>/brand.yaml` found."""
    check_name(name)
    dirs = search_dirs(bundled)
    for d in dirs:
        folder = d / name
        if _is_brand(folder):
            return folder
    raise BrandError(f"brand {name!r} not found. Searched: {searched(dirs)}")


def list_brands(bundled: Path | None = None) -> list[tuple[str, Path]]:
    """(name, folder) for every brand, first match per name, in search order."""
    found: dict[str, Path] = {}
    for d in search_dirs(bundled):
        try:
            folders = sorted(d.iterdir())
        except OSError:
            continue
        for folder in folders:
            if folder.name in found or not _is_brand(folder):
                continue
            found[folder.name] = folder
    return list(found.items())
