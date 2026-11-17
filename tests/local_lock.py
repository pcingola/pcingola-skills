"""Child processes that take the local models lock of `ai_models.local`, for the lock tests of the unit and
integration suites."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from tests.subproc import child_env

# Takes the lock, prints "held" and keeps it until a line arrives on stdin.
HOLDER = """
    import sys
    from ai_models import local
    local.hold_lock()
    print("held", flush=True)
    sys.stdin.readline()
"""


def start(code: str, env: dict[str, str], *args: str) -> subprocess.Popen:
    """Start `code` (dedented) with `python -c` and `args` in environment `env`, with pipes for stdin, stdout and
    stderr."""
    return subprocess.Popen([sys.executable, "-c", textwrap.dedent(code), *args], env=env, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def lock_env(tmp_path: Path) -> dict[str, str]:
    """A child environment whose temporary directory, and so the lock file, is `tmp_path`; offline, with no config."""
    return child_env(TMPDIR=str(tmp_path), TEMP=str(tmp_path), TMP=str(tmp_path), HF_HUB_OFFLINE="1",
                     SKILLS_CONFIG=str(tmp_path / "none.yaml"))
