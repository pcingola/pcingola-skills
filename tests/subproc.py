"""Run code under test in a fresh interpreter with an explicit environment.

Tests never write the process environment. A test that needs a setting runs the
real code in a child process whose environment it states in full."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

from tests.settings_env import isolated


def child_env(env: dict[str, str] | None = None, **extra: str) -> dict[str, str]:
    """`env` (default: this process's environment with the user's settings file
    hidden, see settings_env.isolated) with `extra` added and PYTHONPATH set to
    this interpreter's sys.path, so the child imports the same packages."""
    out = dict(isolated() if env is None else env)
    out.update(extra)
    out["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    return out


def run_python(code: str, env: dict[str, str], timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run `code` (dedented) with `python -c` in environment `env`, for at most `timeout` seconds."""
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, env=env,
                          timeout=timeout)


def run_module(module: str, argv: list[str], env: dict[str, str], timeout: float = 25) -> subprocess.CompletedProcess:
    """`python -m <module> <argv>` in environment `env`, for at most `timeout` seconds (below the 30 s test
    timeout)."""
    return subprocess.run([sys.executable, "-m", module, *argv], env=env, capture_output=True, text=True,
                          timeout=timeout)


def py_value(imports: str, expr: str, env: dict[str, str]) -> object:
    """Run `imports`, then print `expr` as JSON (str() for paths), in a child process with environment `env`;
    return the decoded value. Fails with the child's stderr when it exits non-zero."""
    import json

    done = run_python(f"{imports}\nimport json\nprint(json.dumps({expr}, default=str))", env)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])
