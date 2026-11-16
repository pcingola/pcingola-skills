"""The minimal config.yaml of README.md (the YAML block after `<!-- minimal-config -->`) validates against the
schema, so the README cannot drift from `plugin_settings`."""

import re
from pathlib import Path

import plugin_settings
from plugin_settings import load_config

README = Path(__file__).resolve().parents[3] / "README.md"
MARKER = "<!-- minimal-config -->"


def minimal_config() -> str:
    """The body of the first fenced YAML block after MARKER in README.md."""
    text = README.read_text(encoding="utf-8")
    assert MARKER in text, f"{MARKER} not found in {README}"
    found = re.search(r"^```yaml\n(.*?)^```", text[text.index(MARKER):], re.S | re.M)
    assert found, f"no ```yaml block after {MARKER} in {README}"
    return found.group(1)


def test_readme_minimal_config_validates(tmp_path):
    """The README's minimal file loads with `load_config` with no error and names at least one task. Guards the
    file a user copies by hand."""
    path = tmp_path / "config.yaml"
    path.write_text(minimal_config(), encoding="utf-8")
    plugin_settings.use(path)
    try:
        cfg = load_config()
    finally:
        plugin_settings.use(None)
    assert cfg.tasks
