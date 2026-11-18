"""The directories the short-video wrapper uses, without writing the process environment.

short-video.sh sources plugins/media/lib/uv_env.sh, whose `plugin_env` sets
PLUGIN_ENV_DIR. Under pytest that variable is unset. The tests ask a bash
child for the wrapper's PLUGIN_ENV_DIR, place the node directory and the Manim
environment in it with `config.env_dirs`, and pass the node directory to
`scenes` explicitly; Manim renders run through the wrapper.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from short_video_tool import config

WRAPPER = config.SCRIPTS_DIR / "short-video.sh"
UV_ENV = config.SCRIPTS_DIR.parents[2] / "lib" / "uv_env.sh"


def plugin_env_dir() -> Path:
    """PLUGIN_ENV_DIR as short-video.sh computes it for its scripts directory."""
    done = subprocess.run(
        ["bash", "-c", 'source "$1" && plugin_env "$2" && printf %s "$PLUGIN_ENV_DIR"', "_",
         str(UV_ENV), str(config.SCRIPTS_DIR)],
        capture_output=True, text=True, check=True, timeout=25
    )
    return Path(done.stdout)


ENV_DIR = plugin_env_dir()
_DIRS = config.env_dirs(ENV_DIR)
# Where `short-video.sh setup` installs HyperFrames and GSAP.
NODE_DIR = _DIRS.node_dir
# The Manim environment the wrapper's render uses.
MANIM_VENV = _DIRS.manim_env


def run(*args: str | Path, timeout: float = 25) -> subprocess.CompletedProcess:
    """Run short-video.sh with `args`, for at most `timeout` seconds (below the 30 s test timeout)."""
    return subprocess.run([str(WRAPPER), *map(str, args)], capture_output=True, text=True, timeout=timeout)
