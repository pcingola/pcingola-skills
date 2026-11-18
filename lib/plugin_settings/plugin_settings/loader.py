"""Read, validate and cache config.yaml; format a validation error as one message with a line per problem."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, NoReturn

import yaml
from pydantic import ValidationError

from .paths import config_file, display
from .schema import Config, DiffusersRole, ProviderKind

SETUP_LINE = "The setup:settings skill describes every key and creates the file."
_KINDS = {k.value for k in ProviderKind}
_ROLES = {r.value for r in DiffusersRole}
_FIELD_PREFIX = re.compile(r"^([a-z_]+): (.*)$")

# (path, st_mtime_ns, st_size) -> Config; the long-running Studio server sees edits.
_cache: dict[tuple[Path, int, int], Config] = {}


class ConfigFileError(Exception):
    """The config file is not YAML, not a mapping, or not valid against the schema."""


def error(msg: str) -> NoReturn:
    """Print `Error: <msg>` on stderr and exit 1."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def exit_code(e: SystemExit) -> int:
    """The exit code of `e` as the interpreter sets it: 0 for None, an int code as is, 1 for any other code, which
    is printed on stderr. A CLI's `main` returns it for a `SystemExit` raised in process."""
    if e.code is None or isinstance(e.code, int):
        return e.code or 0
    print(e.code, file=sys.stderr)
    return 1


def clear_cache() -> None:
    _cache.clear()


def _read(p: Path) -> Any:
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigFileError(f"{display(p)} is not valid YAML: {e}\n{SETUP_LINE}") from None


def load_config() -> Config:
    """The validated config file; `Config()` (every default) when the file is missing or empty.
    `ConfigFileError` when it is not YAML, not a mapping, or not valid. Cached per file version."""
    p = config_file()
    if not p.is_file():
        return Config()
    st = p.stat()
    key = (p, st.st_mtime_ns, st.st_size)
    if key in _cache:
        return _cache[key]
    raw = _read(p)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigFileError(f"{display(p)} must be a mapping of sections (providers, tasks, network, huggingface, "
                              f"brand, studio, voiceover)\n{SETUP_LINE}")
    try:
        cfg = Config.model_validate(raw)
    except ValidationError as e:
        raise ConfigFileError(format_errors(p, e)) from None
    for old in [k for k in _cache if k[0] == p]:
        del _cache[old]
    _cache[key] = cfg
    return cfg


def config() -> Config:
    """`load_config()`; on `ConfigFileError`, print the message and exit 1."""
    try:
        return load_config()
    except ConfigFileError as e:
        error(str(e))


def _path(loc: tuple) -> tuple[str, str | None]:
    """(YAML path of a Pydantic `loc`, what the entry it points into is). The discriminated unions' tags are
    dropped: the provider kind after `providers.<name>` and the diffusers role after `models.<m>`; so is the `[key]`
    marker of a mapping key. List indexes are `[i]`."""
    parts = list(loc)
    what = None
    if len(parts) > 2 and parts[0] == "providers" and parts[2] in _KINDS:
        kind = parts.pop(2)
        what = f"kind {kind}"
        if kind == ProviderKind.DIFFUSERS and len(parts) > 4 and parts[2] == "models" and parts[4] in _ROLES:
            what = f"{DiffusersRole(parts.pop(4)).noun()} ({what})"
    out = ""
    for part in parts:
        if part == "[key]":
            continue
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out, what


def _message(err: dict, what: str | None) -> str:
    kind = err["type"]
    if kind == "missing":
        return "required" + (f" for {what}" if what else "")
    if kind == "extra_forbidden":
        return "not a setting" + (f" of {what}" if what else "")
    if kind == "union_tag_not_found":
        return "kind is required (" + ", ".join(sorted(_KINDS)) + ")"
    if kind == "union_tag_invalid":
        return f"kind {err['ctx']['tag']!r} is not one of " + ", ".join(sorted(_KINDS))
    msg = err["msg"]
    return msg.removeprefix("Value error, ")


def format_errors(p: Path, e: ValidationError) -> str:
    """The message of a validation error of file `p`: a line per problem, `<YAML path>: <reason>`."""
    lines = []
    for err in e.errors():
        path, what = _path(err["loc"])
        for m in _message(err, what).splitlines():
            if path and (field := _FIELD_PREFIX.match(m)):  # a model validator's message about one field
                lines.append(f"  {path}.{field[1]}: {field[2]}")
            else:
                lines.append(f"  {path}: {m}" if path else f"  {m}")
    return display(f"{p} is not valid:\n" + "\n".join(lines) + f"\n{SETUP_LINE}")
