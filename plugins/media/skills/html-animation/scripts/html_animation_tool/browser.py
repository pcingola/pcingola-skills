"""Playwright's headless Chromium, installed under the plugin data directory."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .common import HAError, data_dir

# Software WebGL (SwiftShader) for three.js chapters in headless mode.
LAUNCH_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars"]


class Browser:
    """The Chromium headless shell in `<root>` (default `<data dir>/browsers`), used through PLAYWRIGHT_BROWSERS_PATH."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_dir() / "browsers"

    def installed(self) -> bool:
        return any((d / "INSTALLATION_COMPLETE").is_file() for d in self.root.glob("chromium_headless_shell-*"))

    def env(self) -> dict[str, str]:
        """The process environment with PLAYWRIGHT_BROWSERS_PATH pointing at `root`, for Playwright's driver."""
        return {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(self.root)}

    def install(self) -> Path:
        """Install the headless shell of the Chromium that this Playwright version pins (no-op when present)."""
        self.root.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"],
                              env=self.env(), capture_output=True, text=True)
        if done.returncode != 0 or not self.installed():
            raise HAError(f"playwright install chromium failed:\n{done.stdout}{done.stderr}")
        return self.root

    def executable(self) -> Path:
        """The headless shell executable, installed on first use."""
        if not self.installed():
            self.install()
        for name in ("chrome-headless-shell", "headless_shell"):
            found = sorted(self.root.glob(f"chromium_headless_shell-*/*/{name}"))
            if found:
                return found[-1]
        raise HAError(f"no Chromium headless shell executable under {self.root}")
