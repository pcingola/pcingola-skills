"""Settings and project paths for short-video.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.

A film project is a directory given by path. Every file the tool writes for a
project goes inside that directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from plugin_settings import Plugin, error

from . import settings

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
# package.json and package-lock.json for HyperFrames and GSAP.
NODE_SRC = SCRIPTS_DIR / "node"
# Where `setup` installs them: `<PLUGIN_ENV_DIR>/node`, set by the wrapper
# (lib/uv_env.sh) outside the plugin directory, else next to the package files.
NODE_DIR = Path(os.environ["PLUGIN_ENV_DIR"]) / "node" if os.environ.get("PLUGIN_ENV_DIR") else NODE_SRC
# The uv project with Manim Community Edition, for scenes with `Engine: manim`.
MANIM_PROJECT = SCRIPTS_DIR / "manim"
# Its environment sits next to short-video's own under the wrapper's
# PLUGIN_ENV_DIR, named by lib/uv_env.sh's rule for `skills/short-video/scripts/manim`
# (path without `skills/`, `/` as `-`). None when PLUGIN_ENV_DIR is not set:
# Manim then cannot run, since uv's default `.venv` would sit in the plugin directory.
MANIM_ENV_NAME = "short-video-scripts-manim"


def manim_env() -> Path | None:
    """The Manim environment: `<PLUGIN_ENV_DIR parent>/short-video-scripts-manim/.venv`."""
    v = os.environ.get("PLUGIN_ENV_DIR")
    return Path(v).parent / MANIM_ENV_NAME / ".venv" if v else None


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load


def resolve_project(arg: str | None) -> Path:
    """Map a project path (relative or absolute; None = current directory) to a
    directory. A path at or inside `forbidden_project_root` (skill defaults)
    is refused."""
    p = Path(arg).expanduser().resolve() if arg else Path.cwd().resolve()
    forbidden = Path(settings.get()["forbidden_project_root"]).expanduser().resolve()
    if p == forbidden or forbidden in p.parents:
        error(f"{p} is at or inside {forbidden}; put the project elsewhere and pass its path")
    return p
