"""Helpers for pptx-author integration tests.

`pptx-author` carries no code: it is SKILL.md and references/. Its template path
fills the `neutral` brand's template of the brand plugin
(`brands/neutral/pptx/presentation.pptx`). These tests drive that template through
another skill's CLI, `pptx`, the way the template path does. Hence PPTX_TOOL below points at `pptx`, not
at a wrapper of this skill's own — there isn't one.

The suite runs in the `pptx` skill's project (`uv run --project plugins/docs/skills/pptx/scripts`).
"""

import shutil
import subprocess
from pathlib import Path

from tests.options import keep_tmp

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_DIR / "tests" / "data"
TMP_DIR = DATA_DIR / "tmp_pptx_author"

# pptx-author has no scripts/ of its own; its templates are read through pptx.
PPTX_TOOL = str(
    PROJECT_DIR / "plugins" / "docs" / "skills" / "pptx" / "scripts" / "pptx.sh"
)

BRAND_PPTX_DIR = (
    PROJECT_DIR / "plugins" / "brand" / "skills" / "brand" / "brands" / "neutral" / "pptx"
)
PRESENTATION_TEMPLATE = BRAND_PPTX_DIR / "presentation.pptx"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PPTX_TOOL, *args], capture_output=True, text=True, cwd=PROJECT_DIR)


def fresh_dir(name: str) -> Path:
    """Create (or recreate) a subdirectory under TMP_DIR and return its path."""
    d = TMP_DIR / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def cleanup_dir(d: Path) -> None:
    if not keep_tmp():
        shutil.rmtree(d, ignore_errors=True)


def write_readme(d: Path, description: str) -> None:
    """Write a README.txt describing the test outputs. Only with `pytest --keep-tmp`."""
    if not keep_tmp():
        return
    (d / "README.txt").write_text(description.strip() + "\n")
