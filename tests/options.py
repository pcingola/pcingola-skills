"""Command-line options of the test run that helper modules read.

`tests/conftest.py` registers the options and records their values here in `pytest_configure`, before any test
module runs; helpers read them through the functions below.
"""

from __future__ import annotations

_values: dict[str, object] = {}


def record(config) -> None:
    """Record the option values of the pytest `config`."""
    _values["keep_tmp"] = bool(config.getoption("keep_tmp"))


def keep_tmp() -> bool:
    """Whether `--keep-tmp` was given: keep test output files (and add the pptx summary slides)."""
    return bool(_values.get("keep_tmp", False))
