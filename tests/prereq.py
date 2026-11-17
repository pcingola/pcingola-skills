"""`requires` and `require`: a test or test class fails with a clear message when a tool, key or
model it needs is missing. Tests never skip."""
from __future__ import annotations

import functools
import json
import urllib.request

from plugin_settings import OLLAMA_URL

# The Ollama server of the `ollama` provider of tests/config.yaml, which sets no base_url.
OLLAMA = OLLAMA_URL.removesuffix("/v1")


def require_ollama(*tasks: str) -> None:
    """Fail the test when Ollama does not answer at OLLAMA, or does not hold the model of one of `tasks` in
    tests/config.yaml."""
    from tests.settings_env import task_model

    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            names = [m["name"] for m in json.load(r)["models"]]
    except (OSError, KeyError, ValueError):
        raise AssertionError(f"missing prerequisite: Ollama does not answer at {OLLAMA}; start it") from None
    held = {*names, *(n.removesuffix(":latest") for n in names)}
    missing = [m for m in (task_model(t).split(":", 1)[1] for t in tasks) if m not in held]
    assert not missing, f"missing prerequisite: Ollama lacks {', '.join(missing)}; run ollama pull {' '.join(missing)}"


def require(ok: object, reason: str) -> None:
    """Fail the running test with `reason` when `ok` is false."""
    if not ok:
        raise AssertionError(f"missing prerequisite: {reason}")


def requires(ok: object, reason: str):
    """Decorate a test function or a unittest.TestCase class; when `ok` is false
    the test fails with `reason`."""
    def check() -> None:
        require(ok, reason)

    def deco(obj):
        if isinstance(obj, type):
            setup = obj.__dict__.get("setUpClass")
            parent = super(obj, obj).setUpClass if setup is None else None

            def setUpClass(cls) -> None:
                check()
                if setup is not None:
                    setup.__func__(cls)
                else:
                    parent()
            obj.setUpClass = classmethod(setUpClass)
            return obj

        @functools.wraps(obj)
        def wrapper(*args, **kwargs):
            check()
            return obj(*args, **kwargs)
        return wrapper
    return deco
