"""The style catalogue and the brand names, read from the brand plugin's files.

The brand plugin's folder comes from `claude plugin list --json`: the `brand@<marketplace>` entry of the marketplace
of the listed `studio@<marketplace>` entry, else the first `brand@*` entry; its `readFromFolder`, else its
`installPath`. When the command is missing, fails or
lists no brand plugin, the folder is the `brand` directory next to the studio plugin (a repository checkout).

The styles are `skills/style/references/catalogue.json` of that folder, each `sample` (relative to `skills/style/`)
made absolute. The brands are the folders holding a `brand.yaml` in its `skills/brand/brands/`, then in each
directory of `BRAND_PATH`, first match per name, as the brand CLI lists them; `BRAND_PATH` is the setting the
brand CLI reads (`plugin_settings.get`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from plugin_settings import MANIFEST, get

from .paths import log

PLUGIN_LIST = ("plugin", "list", "--json")
PLUGIN_LIST_TIMEOUT = 10.0
BRAND_PLUGIN = "brand"
STYLE_DIR = Path("skills") / "style"
CATALOGUE_FILE = STYLE_DIR / "references" / "catalogue.json"
BUNDLED_BRANDS = Path("skills") / "brand" / "brands"
BRAND_FILE = "brand.yaml"


def plugin_list() -> list | None:
    """The entries printed by `claude plugin list --json`, `claude` found with shutil.which (so `claude.cmd` on
    Windows); None when the command is missing, fails, times out or prints no JSON list."""
    command = f"claude {' '.join(PLUGIN_LIST)}"
    claude = shutil.which("claude")
    if claude is None:
        log(f"studio server: {command}: claude not found on PATH")
        return None
    try:
        r = subprocess.run((claude, *PLUGIN_LIST), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=PLUGIN_LIST_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"studio server: {command}: {e}")
        return None
    if r.returncode != 0:
        log(f"studio server: {command} exited with {r.returncode}: {r.stderr.strip()}")
        return None
    try:
        entries = json.loads(r.stdout)
    except ValueError:
        log(f"studio server: {command} printed no JSON")
        return None
    return entries if isinstance(entries, list) else None


def brand_from_list(entries: list) -> Path | None:
    """The folder of the `brand@*` entry of the `studio@*` entry's marketplace, else of the first `brand@*` entry
    (later ones when its folder is missing): its `readFromFolder`, else its `installPath`, when a directory.
    Entries with `enabled: false` are ignored."""
    entries = [e for e in entries
               if isinstance(e, dict) and isinstance(e.get("id"), str) and e.get("enabled") is not False]
    ids = [e["id"] for e in entries]
    studio = next((i for i in ids if i.startswith("studio@")), None)
    own = f"{BRAND_PLUGIN}@{studio.split('@', 1)[1]}" if studio else None
    brands = [e for e in entries if e["id"].startswith(f"{BRAND_PLUGIN}@")]
    brands.sort(key=lambda e: e["id"] != own)
    for entry in brands:
        for key in ("readFromFolder", "installPath"):
            folder = entry.get(key)
            if isinstance(folder, str) and folder and Path(folder).is_dir():
                return Path(folder)
    return None


def find_brand_plugin(studio_root: Path, list_plugins: Callable[[], list | None] = plugin_list) -> Path | None:
    """The brand plugin's folder (module docstring), None when neither the plugin list nor the sibling has it."""
    entries = list_plugins()
    if entries is not None:
        found = brand_from_list(entries)
        if found is not None:
            return found
    sibling = studio_root.parent / BRAND_PLUGIN
    return sibling if (sibling / MANIFEST).is_file() else None


def brand_path() -> str:
    """`BRAND_PATH` as the brand plugin's CLI reads it: the setting of the config file, else empty."""
    return get("BRAND_PATH", "") or ""


def list_brands(brand_root: Path, path_setting: str) -> list[str]:
    """Names of the brand folders in the bundled directory, then each `path_setting` entry (colon-separated, `~`
    expanded, empty entries, non-directories and repeated directories skipped), first match per name."""
    candidates = [brand_root / BUNDLED_BRANDS]
    candidates += [Path(e.strip()).expanduser() for e in path_setting.split(":") if e.strip()]
    names: list[str] = []
    seen: set[Path] = set()
    for d in candidates:
        if not d.is_dir() or d.resolve() in seen:
            continue
        seen.add(d.resolve())
        try:
            folders = sorted(d.iterdir())
        except OSError:
            continue
        names += [f.name for f in folders if f.name not in names and (f / BRAND_FILE).is_file()]
    return names


def read_catalogue(brand_root: Path | None) -> tuple[dict, frozenset[Path]]:
    """`({"styles", "brands"}, sample paths)`. Without the brand plugin, empty lists and an `error`; with a missing
    or bad catalogue file, no styles and an `error`, the brands still listed. A style without a string `name`, or
    with a `sample` that is neither a string nor null, is left out; a null `sample` (no sample image yet) stays null."""
    if brand_root is None:
        return {"styles": [], "brands": [], "error": "the brand plugin was not found"}, frozenset()
    brands = list_brands(brand_root, brand_path())
    path = brand_root / CATALOGUE_FILE
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"styles": [], "brands": brands, "error": f"cannot read the style catalogue {path}: {e}"}, frozenset()
    if not isinstance(entries, list):
        return {"styles": [], "brands": brands, "error": f"the style catalogue {path} is not a list"}, frozenset()
    styles, samples = [], set()
    for s in entries:
        if not (isinstance(s, dict) and isinstance(s.get("name"), str) and "sample" in s
                and (s["sample"] is None or isinstance(s["sample"], str))):
            log(f"studio server: {path}: a style without name or sample left out")
            continue
        if s["sample"] is None:
            styles.append({**s, "sample": None})
            continue
        sample = (brand_root / STYLE_DIR / s["sample"]).resolve()
        styles.append({**s, "sample": str(sample)})
        samples.add(sample)
    return {"styles": styles, "brands": brands}, frozenset(samples)
