"""Run the voiceover CLI as a subprocess with explicit extra environment variables."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "plugins/media/skills/voiceover/scripts"


def voiceover(*argv: str, timeout: float = 25, **env: str) -> subprocess.CompletedProcess:
    full = {**os.environ, **env, "PYTHONPATH": os.pathsep.join([str(SCRIPTS), os.environ.get("PYTHONPATH", "")])}
    return subprocess.run([sys.executable, "-m", "voiceover_tool", *argv], env=full, capture_output=True, text=True,
                          timeout=timeout)
