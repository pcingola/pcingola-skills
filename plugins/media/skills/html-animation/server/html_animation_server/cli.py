"""The skill's CLI wrapper (`../scripts/html-animation.sh`), run as a subprocess for `still`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .http_error import HttpError
from .mark import Mark

CLI_PATH = Path(__file__).resolve().parents[2] / "scripts" / "html-animation.sh"
TIMEOUT = 180
# Variables of this server's own uv environment, which the CLI wrapper sets again for its own project.
ENV_DROP = ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONPYCACHEPREFIX", "PLUGIN_ENV_DIR")


class AnimationCli:
    def __init__(self, path: str | Path = CLI_PATH) -> None:
        self.path = Path(path)

    def run(self, *args: str) -> dict:
        """Runs one command and returns its JSON output; 502 with the CLI's stderr when it fails."""
        env = {k: v for k, v in os.environ.items() if k not in ENV_DROP}
        try:
            done = subprocess.run([str(self.path), *args], capture_output=True, text=True, timeout=TIMEOUT, env=env,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HttpError(502, f"html-animation {args[0]} failed: {e}") from None
        if done.returncode != 0:
            raise HttpError(502, f"html-animation {args[0]} exited {done.returncode}: {done.stderr.strip()[-2000:]}")
        try:
            value = json.loads(done.stdout)
        except ValueError:
            raise HttpError(502, f"html-animation {args[0]} printed no JSON: {done.stdout[-500:]}") from None
        return value if isinstance(value, dict) else {"value": value}

    def still(self, folder: Path, t: float, mark: Mark, out: Path) -> Path:
        """Renders the frame at `t` with the mark drawn, into `out`."""
        result = self.run("still", str(folder), "--at", f"{t:.3f}", "--mark", mark.cli_arg(), "--out", str(out))
        png = Path(str(result.get("png") or out))
        if not png.is_file():
            raise HttpError(502, f"html-animation still wrote no PNG at {png}")
        return png
