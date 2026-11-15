"""Settings of the skills: one file, `config.yaml`, and the data directory of each plugin.

The file is `$SKILLS_CONFIG` when set, else `<config dir>/plugins/data/config.yaml`.
<config dir> is `$CLAUDE_CONFIG_DIR` when set, else `~/.claude`. Its sections:

    providers, models, diffusers   the model layer (ai_models)
    settings                        every other setting, `KEY: value`

`get(key)` returns `settings.<key>` of the file, else the variable `key` of the
process environment, else the default. A missing file has no settings.
`Plugin.load()` exports the settings of ENV_KEYS to the process environment,
because libraries and child processes read them there (proxies, TLS, Hugging
Face). The file never sets CLAUDE_CONFIG_DIR, CLAUDE_PLUGIN_DATA or
SKILLS_CONFIG: they decide where the file and the data directory are.

<plugin data dir> is `$CLAUDE_PLUGIN_DATA` when set, else the directory Claude
Code assigns: `<config dir>/plugins/data/<plugin>-<marketplace>`, characters
other than letters, digits, `_` and `-` replaced by `-`. <plugin> is the `name`
in the plugin's `.claude-plugin/plugin.json`; <marketplace> is the `name` in
the `.claude-plugin/marketplace.json` of the nearest directory above the plugin
(a plugin loaded in place), else the marketplace directory of a cache copy
(`<config dir>/plugins/cache/<marketplace>/<plugin>/<version>`).

A skill binds to its plugin with `Plugin.of(__file__)`.

`require(key)` returns a setting or exits when it is missing; `invalid(key,
value, expected)` exits for a value the caller rejects, naming where the value
was set. Both name the config file and whether it exists, with home-directory
paths shown as `~`. `error()` is for errors that are not about a setting.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import yaml

MANIFEST = Path(".claude-plugin") / "plugin.json"
MARKETPLACE_MANIFEST = Path(".claude-plugin") / "marketplace.json"
# Names another config file; read from the process environment only.
CONFIG_ENV = "SKILLS_CONFIG"
# Settings that Plugin.load exports to the process environment: read there by
# httpx, urllib, requests and Python's ssl (proxies, SSL_CERT_FILE), Node.js child
# processes (NODE_EXTRA_CA_CERTS) and huggingface_hub (HF_HOME, HF_TOKEN).
ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS",
            "HF_HOME", "HF_TOKEN")
SETUP_LINE = "The setup:settings skill describes every setting and creates the file."

# The file set by `use`; it wins over the environment.
_used: Path | None = None


class ConfigFileError(Exception):
    """The config file is not valid YAML or not a mapping."""


def error(msg: str) -> NoReturn:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def config_dir() -> Path:
    """Claude Code's configuration directory: `$CLAUDE_CONFIG_DIR`, else `~/.claude`."""
    v = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(v or "~/.claude").expanduser()


def use(file: str | Path | None) -> None:
    """Read the config from `file` from now on in this process (None: back to the default)."""
    global _used
    _used = Path(file).expanduser() if file else None


def config_file() -> Path:
    """The config file: the one set by `use`, else `$SKILLS_CONFIG`, else
    `<config dir>/plugins/data/config.yaml`."""
    if _used is not None:
        return _used
    v = os.environ.get(CONFIG_ENV, "").strip()
    return Path(v).expanduser() if v else config_dir() / "plugins" / "data" / "config.yaml"


def read_config() -> dict[str, Any]:
    """The parsed config file, {} when it is missing or empty; `ConfigFileError`
    when it is not valid YAML or not a mapping."""
    p = config_file()
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigFileError(f"{p} is not valid YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigFileError(f"{p} must be a mapping with the sections providers, models, diffusers, settings")
    return data


def settings() -> dict[str, str]:
    """The `settings` section as strings (`true`/`false` for booleans); a key
    with an empty YAML value (null) is left out. Exits on a malformed file."""
    try:
        raw = read_config().get("settings") or {}
    except ConfigFileError as e:
        error(str(e))
    if not isinstance(raw, dict):
        error(f"`settings` in {_display(config_file())} must be a mapping of KEY: value")
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            error(f"settings.{k} in {_display(config_file())} must be a single value")
        out[str(k)] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return out


def get(key: str, default: str | None = None) -> str | None:
    """`settings.<key>` of the config file, else the process environment, else `default`."""
    v = settings().get(key)
    if v is None:
        v = os.environ.get(key)
    return default if v is None else v


def export() -> None:
    """Copy the settings of ENV_KEYS that the file sets to the process environment."""
    s = settings()
    for k in ENV_KEYS:
        if k in s:
            os.environ[k] = s[k]


def _find_up(path: Path, rel: Path) -> Path | None:
    for d in (path, *path.parents):
        if (d / rel).is_file():
            return d / rel
    return None


def _json_name(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        return None
    return name if isinstance(name, str) and name else None


def _marketplace_name(root: Path, plugin: str) -> str | None:
    """The marketplace of the plugin at `root`, from a marketplace manifest above
    it or from the cache layout `<config dir>/plugins/cache/<marketplace>/<plugin>/<version>`."""
    name = _json_name(_find_up(root.parent, MARKETPLACE_MANIFEST))
    if name:
        return name
    real = root.resolve()
    cache = (config_dir() / "plugins" / "cache").resolve()
    if len(real.parents) > 2 and real.parents[2] == cache and real.parent.name == plugin:
        return real.parents[1].name
    return None


def _display(path: Path) -> str:
    """`path` with the home directory shown as `~`."""
    try:
        rel = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    return "~" if rel == Path(".") else f"~/{rel}"


def _where() -> str:
    """The line of a settings error that names the config file."""
    p = config_file()
    return (f"Settings are read from {_display(p)} ({'found' if p.is_file() else 'not found'}), "
            "section `settings`, then from the process environment.")


def require(key: str) -> str:
    """The value of `key` stripped of whitespace, or exit with an error naming the
    config file. An empty or blank value is missing."""
    v = (get(key) or "").strip()
    if not v:
        error(f"{key} is not set.\n{_where()}\n"
              f"Add it to that file:\n  settings:\n    {key}: <value>\n{SETUP_LINE}")
    return v


def invalid(key: str, value: str, expected: str) -> NoReturn:
    """Exit with an error saying that `value` of `key` is not valid (`expected`
    says what is), naming where it was set."""
    where = f"settings.{key} in {_display(config_file())}" if key in settings() else "the process environment"
    error(f"{key}={value!r} (set in {where}) is not valid: {expected}.\n{_where()}\n{SETUP_LINE}")


@dataclass(frozen=True)
class Plugin:
    """A plugin: its directory (None when no manifest was found) and its name
    (None when the manifest has none)."""

    name: str | None
    root: Path | None = None

    @classmethod
    def of(cls, path: str | Path) -> Plugin:
        """The plugin holding `path` (a file or directory inside it)."""
        manifest = _find_up(Path(path).resolve(), MANIFEST)
        return cls(_json_name(manifest), manifest.parent.parent if manifest else None)

    def data_dir(self) -> Path:
        """`$CLAUDE_PLUGIN_DATA` when set, else `<config dir>/plugins/data/<plugin>-<marketplace>`
        (exit with an error when the plugin or marketplace name is unknown)."""
        v = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
        if v:
            return Path(v).expanduser()
        if self.name is None or self.root is None:
            error(f"no plugin name in {self.root / MANIFEST if self.root else MANIFEST}; set CLAUDE_PLUGIN_DATA")
        marketplace = _marketplace_name(self.root, self.name)
        if marketplace is None:
            error(f"cannot tell the marketplace of the plugin in {self.root}; set CLAUDE_PLUGIN_DATA")
        data_id = re.sub(r"[^A-Za-z0-9_-]", "-", f"{self.name}-{marketplace}")
        return config_dir() / "plugins" / "data" / data_id

    def load(self) -> None:
        """Read the config file (exit when it is malformed) and export ENV_KEYS."""
        export()

    def get(self, key: str, default: str | None = None) -> str | None:
        return get(key, default)

    def require(self, key: str) -> str:
        return require(key)

    def invalid(self, key: str, value: str, expected: str) -> NoReturn:
        invalid(key, value, expected)


__all__ = [
    "CONFIG_ENV", "ENV_KEYS", "MANIFEST", "ConfigFileError", "Plugin", "config_dir", "config_file", "error",
    "export", "get", "invalid", "read_config", "require", "settings", "use",
]
