#!/usr/bin/env python3
"""
ClaudeRunner — launches Claude CLI sub-agent invocations and parses their terminal signals.

The batch loop builds a prompt string, calls runner.run(), then calls
runner.classify() to determine success or failure.

Signal protocol
---------------
Agents end their response with exactly one terminal signal line:

    DONE: <payload>             — success; payload is job-specific
    ERROR_TRANSIENT: <payload>  — transient failure (network, timeout); safe to retry
    ERROR_FATAL: <payload>      — permanent failure (corrupt file, bad format); skip

The colon is the separator between the keyword and the payload.
Signal keywords are the string values of Status.DONE, Status.ERROR_TRANSIENT,
Status.ERROR_FATAL, so callers construct signal lines as f"{Status.DONE}: {payload}".
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import format_stream as fmt
from .status import Status  # noqa: F401 (re-exported for callers)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_name(path: str) -> str:
    """Return a filesystem-safe version of a full path (separators and special chars → underscores)."""
    return str(path).translate(str.maketrans(' /\\:*?"<>|\'', "__________-"))


class ClaudeRunner:
    def __init__(self, cwd: Path, runs_dir: Path, settings: str = "") -> None:
        """
        Args:
            cwd:      Working directory the Claude CLI is invoked from.
            runs_dir: Directory where per-invocation stream-json logs are written.
            settings: Optional path passed as `claude --settings <settings>`. Omitted if empty.
        """
        self.cwd = cwd
        self.runs_dir = runs_dir
        self.settings = settings
        runs_dir.mkdir(parents=True, exist_ok=True)

    def run(self, prompt: str, name: str) -> tuple[str, int]:
        """
        Invoke the Claude CLI with the given prompt string.

        Streams the Claude CLI's stream-json output to a timestamped log file under
        runs_dir and to stdout (via format_stream for human-readable live display).

        Args:
            prompt: The fully-rendered prompt string to pass to Claude via -p.
            name:   A short label used to name the log file.

        Returns:
            (result_text, exit_code) where result_text is the final assistant message
            extracted from the stream-json log, and exit_code is the Claude CLI exit code.
        """
        run_log = self.runs_dir / f"{timestamp()}_{name}.log"
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            *(["--settings", self.settings] if self.settings else []),
            "--output-format", "stream-json",
            "--verbose",
            "-p", prompt,
        ]
        with open(run_log, "w") as log_fh:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log_fh, cwd=self.cwd)
            for raw in proc.stdout:
                line = raw.decode(errors="replace")
                log_fh.write(line)
                log_fh.flush()
                try:
                    fmt.format_event(json.loads(line))
                except json.JSONDecodeError:
                    pass
            proc.wait()
        return self._extract_result(run_log), proc.returncode

    def classify(self, result_text: str, exit_code: int) -> tuple[Status, str]:
        """
        Parse the terminal signal line from the agent's final response text.

        Scans result_text lines in reverse for one starting with a known Status
        keyword followed by a colon. Returns on the first match.

        Args:
            result_text: The full text of the agent's final response.
            exit_code:   The Claude CLI process exit code (used in fallback error message).

        Returns:
            (status, reason):
                - status is Status.DONE on success, ERROR_TRANSIENT or ERROR_FATAL on failure.
                - reason is empty on success, human-readable on failure.
                - No signal line ⇒ ERROR_TRANSIENT.
        """
        for line in reversed(result_text.splitlines()):
            for status in (Status.DONE, Status.ERROR_FATAL, Status.ERROR_TRANSIENT):
                if line.startswith(f"{status}:"):
                    sep = "—" if "—" in line else ("-" if " - " in line else None)
                    reason = line.split(sep, 1)[-1].strip() if sep else ""
                    return status, reason
        return Status.ERROR_TRANSIENT, f"no {Status.DONE}: signal in result (exit={exit_code})"

    def _extract_result(self, log_path: Path) -> str:
        """
        Extract the final assistant message from a Claude CLI stream-json log file.

        The Claude CLI emits one JSON object per line. The final assistant message
        appears as: {"type": "result", "result": "<full response text>", ...}
        This method scans the log for that line and returns the response text.
        Returns an empty string if no result line is found (e.g. process crashed).
        """
        result_text = ""
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "result":
                            result_text = obj.get("result", "")
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return result_text
