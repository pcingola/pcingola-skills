"""Environment for running a skill wrapper without the user's settings file,
and `write_config` for a test's own settings file.

Settings come only from the settings file `<config dir>/plugins/data/config.yaml`,
so the user's file would set them for the code under test. `isolated` points
HOME, CLAUDE_CONFIG_DIR and CLAUDE_PLUGIN_DATA at a temporary directory of this
process, where no settings file exists. A test that needs a setting writes a
config.yaml with `write_config` and passes its path in SKILLS_CONFIG; TEST_CONFIG
is tests/config.yaml with `~` already expanded to the real home. uv keeps
its real cache, Python installs and configuration, and git its global
configuration (credential helper for the git dependencies); the wrapper's
environment is built once per test process under the temporary plugin data
directory.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# The marketplace name in this repository's manifest; plugin data directories
# are <config dir>/plugins/data/<plugin>-<MARKETPLACE>.
MARKETPLACE = json.loads(
    (Path(__file__).resolve().parents[1] / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
)["name"]

_ROOT = Path(tempfile.mkdtemp(prefix="skills-settings-"))
atexit.register(shutil.rmtree, _ROOT, ignore_errors=True)


def _expand_home(value: object) -> object:
    """`value` with every string that starts with `~` expanded with this process's HOME, in nested maps and lists."""
    if isinstance(value, dict):
        return {k: _expand_home(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_home(v) for v in value]
    return str(Path(value).expanduser()) if isinstance(value, str) and value.startswith("~") else value


def _test_config() -> Path:
    """tests/config.yaml written under the temporary directory with its `~` paths expanded with the real HOME, so a
    child process with the temporary HOME of `isolated` uses the same weight directories and Hugging Face cache."""
    import yaml

    data = yaml.safe_load((Path(__file__).resolve().parent / "config.yaml").read_text(encoding="utf-8"))
    path = _ROOT / "test-config.yaml"
    path.write_text(yaml.safe_dump(_expand_home(data)), encoding="utf-8")
    return path


# The settings file of the unit and integration tests: the tiny models tests load or call (_test_config).
TEST_CONFIG = _test_config()


def config_sections() -> dict:
    """The sections of TEST_CONFIG."""
    import yaml

    return yaml.safe_load(TEST_CONFIG.read_text(encoding="utf-8"))


def task_model(task: str) -> str:
    """The model id `<provider>:<model>` of `task` in TEST_CONFIG."""
    return config_sections()["tasks"][task]


def model_entry(task: str) -> dict:
    """The entry `providers.<provider>.models.<model>` of the model of `task` in TEST_CONFIG."""
    provider, model = task_model(task).split(":", 1)
    return config_sections()["providers"][provider]["models"][model]


def _uv_dir(*args: str) -> str:
    return subprocess.run(["uv", *args], capture_output=True, text=True, check=True).stdout.strip()


# Resolved with the real HOME, before any environment is changed.
_KEEP = {
    "UV_CACHE_DIR": _uv_dir("cache", "dir"),
    "UV_PYTHON_INSTALL_DIR": _uv_dir("python", "dir"),
    "XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"),
}
if (Path.home() / ".gitconfig").is_file():
    _KEEP["GIT_CONFIG_GLOBAL"] = str(Path.home() / ".gitconfig")


def write_config(path: Path, **sections: object) -> Path:
    """Write a config.yaml at `path` with `sections` (providers, tasks, network, huggingface, brand, studio,
    voiceover); return `path`."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(sections), encoding="utf-8")
    return path


def overrides(env: dict[str, str] | None = None) -> dict[str, str]:
    """The variables `isolated` changes in `env` (default os.environ): HOME,
    CLAUDE_CONFIG_DIR and CLAUDE_PLUGIN_DATA in the temporary directory, the
    uv and git locations of _KEEP when unset."""
    env = os.environ if env is None else env
    (_ROOT / "home").mkdir(exist_ok=True)
    out = {k: v for k, v in _KEEP.items() if k not in env}
    out["HOME"] = str(_ROOT / "home")
    out["CLAUDE_CONFIG_DIR"] = str(_ROOT / "config")
    out["CLAUDE_PLUGIN_DATA"] = str(_ROOT / "plugin-data")
    return out


def isolated(env: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of `env` (default os.environ) with `overrides` applied and SKILLS_CONFIG removed."""
    base = {k: v for k, v in (os.environ if env is None else env).items() if k != "SKILLS_CONFIG"}
    return {**base, **overrides(base)}

