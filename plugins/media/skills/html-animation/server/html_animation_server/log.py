"""Diagnostics go to stderr: stdout carries the JSON lines for the mod only."""

from __future__ import annotations

import sys


def log(text: str) -> None:
    sys.stderr.write(text + "\n")
    sys.stderr.flush()
