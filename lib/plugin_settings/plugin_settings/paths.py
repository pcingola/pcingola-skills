"""Where the settings file is: `use`, `config_dir`, `config_file`; `display` shows a home path as `~`."""

from __future__ import annotations

import os
from pathlib import Path

# Names another config file; read from the process environment only.
CONFIG_ENV = "SKILLS_CONFIG"

# The file set by `use`; it wins over SKILLS_CONFIG.
_used: Path | None = None


def config_dir() -> Path:
    """Claude Code's configuration directory: `$CLAUDE_CONFIG_DIR`, else `~/.claude`."""
    v = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(v or "~/.claude").expanduser()


def use(file: str | Path | None) -> None:
    """Read the config from `file` from now on in this process (None: back to the default). Clears the cache of
    loaded files, so a file rewritten within one timestamp tick is read again."""
    global _used
    from .loader import clear_cache

    _used = Path(file).expanduser() if file else None
    clear_cache()


def config_file() -> Path:
    """The config file: the one set by `use`, else `$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`."""
    if _used is not None:
        return _used
    v = os.environ.get(CONFIG_ENV, "").strip()
    return Path(v).expanduser() if v else config_dir() / "plugins" / "data" / "config.yaml"


def display(text: str | Path) -> str:
    """`text` (a path or a message) with the home directory shown as `~`."""
    home = str(Path.home())
    s = str(text)
    return s.replace(home, "~") if home not in ("", "/") else s
