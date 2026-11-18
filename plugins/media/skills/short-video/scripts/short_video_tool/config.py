"""Settings and project paths for short-video.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.

A film project is a directory given by path. Every file the tool writes for a
project goes inside that directory.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from plugin_settings import Plugin, error

from . import settings

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
# package.json and package-lock.json for HyperFrames and GSAP.
NODE_SRC = SCRIPTS_DIR / "node"
# The uv project with Manim Community Edition, for scenes with `Engine: manim`.
MANIM_PROJECT = SCRIPTS_DIR / "manim"
# The Manim environment's directory name next to short-video's own, by lib/uv_env.sh's
# rule for `skills/short-video/scripts/manim` (path without `skills/`, `/` as `-`).
MANIM_ENV_NAME = "short-video-scripts-manim"


@dataclass(frozen=True)
class EnvDirs:
    """Where `setup` installs HyperFrames and GSAP (`node_dir`), and the Manim
    environment (`manim_env`, None when it has no place outside the plugin directory)."""
    node_dir: Path
    manim_env: Path | None


def env_dirs(plugin_env_dir: Path | None) -> EnvDirs:
    """The node directory and the Manim environment for the plugin environment
    directory `plugin_env_dir` (the one the wrapper short-video.sh sets through
    lib/uv_env.sh). With a directory: `<dir>/node` and
    `<dir parent>/short-video-scripts-manim/.venv`. With None: the node directory
    next to the package files, and no Manim environment, since uv's default
    `.venv` would sit in the plugin directory."""
    if plugin_env_dir is None:
        return EnvDirs(NODE_SRC, None)
    return EnvDirs(plugin_env_dir / "node", plugin_env_dir.parent / MANIM_ENV_NAME / ".venv")


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
load_settings = PLUGIN.load


def resolve_project(arg: str | None) -> Path:
    """Map a project path (relative or absolute; None = current directory) to a
    directory. A path at or inside `forbidden_project_root` (skill defaults)
    is refused; a null `forbidden_project_root` refuses no path."""
    p = Path(arg).expanduser().resolve() if arg else Path.cwd().resolve()
    root = settings.get().get("forbidden_project_root")
    if not root:
        return p
    forbidden = Path(root).expanduser().resolve()
    if p == forbidden or forbidden in p.parents:
        error(f"{p} is at or inside {forbidden}; put the project elsewhere and pass its path")
    return p
