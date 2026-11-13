"""`requires`: a test or test class fails with a clear message when a tool, key or
model it needs is missing. Tests never skip."""
from __future__ import annotations

import functools


def requires(ok: object, reason: str):
    """Decorate a test function or a unittest.TestCase class; when `ok` is false
    the test fails with `reason`."""
    def check() -> None:
        if not ok:
            raise AssertionError(f"missing prerequisite: {reason}")

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
