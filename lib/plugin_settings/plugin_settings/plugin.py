"""`Plugin`: a plugin's name, directory and data directory; `load` reads the config and exports it."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .env_export import export
from .loader import config, error
from .paths import config_dir
from .schema import Config

MANIFEST = Path(".claude-plugin") / "plugin.json"
MARKETPLACE_MANIFEST = Path(".claude-plugin") / "marketplace.json"


def _find_up(path: Path, rel: Path) -> Path | None:
    for d in (path, *path.parents):
        if (d / rel).is_file():
            return d / rel
    return None


def _json_name(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        return None
    return name if isinstance(name, str) and name else None


def _marketplace_name(root: Path, plugin: str) -> str | None:
    """The marketplace of the plugin at `root`, from a marketplace manifest above
    it or from the cache layout `<config dir>/plugins/cache/<marketplace>/<plugin>/<version>`."""
    name = _json_name(_find_up(root.parent, MARKETPLACE_MANIFEST))
    if name:
        return name
    real = root.resolve()
    cache = (config_dir() / "plugins" / "cache").resolve()
    if len(real.parents) > 2 and real.parents[2] == cache and real.parent.name == plugin:
        return real.parents[1].name
    return None


@dataclass(frozen=True)
class Plugin:
    """A plugin: its directory (None when no manifest was found) and its name
    (None when the manifest has none)."""

    name: str | None
    root: Path | None = None

    @classmethod
    def of(cls, path: str | Path) -> Plugin:
        """The plugin holding `path` (a file or directory inside it)."""
        manifest = _find_up(Path(path).resolve(), MANIFEST)
        return cls(_json_name(manifest), manifest.parent.parent if manifest else None)

    def data_dir(self) -> Path:
        """`$CLAUDE_PLUGIN_DATA` when set, else `<config dir>/plugins/data/<plugin>-<marketplace>`
        (exit with an error when the plugin or marketplace name is unknown)."""
        v = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
        if v:
            return Path(v).expanduser()
        if self.name is None or self.root is None:
            error(f"no plugin name in {self.root / MANIFEST if self.root else MANIFEST}; set CLAUDE_PLUGIN_DATA")
        marketplace = _marketplace_name(self.root, self.name)
        if marketplace is None:
            error(f"cannot tell the marketplace of the plugin in {self.root}; set CLAUDE_PLUGIN_DATA")
        data_id = re.sub(r"[^A-Za-z0-9_-]", "-", f"{self.name}-{marketplace}")
        return config_dir() / "plugins" / "data" / data_id

    def load(self) -> Config:
        """The config (`config()`: exit when the file is not valid), exported to the process environment
        (`export`)."""
        cfg = config()
        export(cfg)
        return cfg
