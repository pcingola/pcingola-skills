"""Path checks, slugs, safe file names, data URLs and the log on stderr.

Every path from a request body or query is resolved (symbolic links followed) before it is compared with a
directory, so a link inside the root that points outside it is outside.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path


def log(text: str) -> None:
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


class HttpError(Exception):
    """An error answered with `status` and `{"error": message}`, plus the keys of `extra`."""

    def __init__(self, status: int, message: str, extra: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


def read_json(path: Path) -> object | None:
    """The JSON in `path`, or None when it is missing or not valid JSON (for example while it is being written)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def positive(body: dict, key: str) -> int:
    """`body[key]`, which must be a positive integer (not a bool); 400 otherwise."""
    v = body.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        raise HttpError(400, f"{key} must be a positive integer")
    return v


def resolve_abs(value: object, what: str) -> Path:
    """`value` as a resolved absolute path; 400 when it is not an absolute path string."""
    if not isinstance(value, str) or not value or "\0" in value or not os.path.isabs(value):
        raise HttpError(400, f"{what} must be an absolute path")
    return Path(value).resolve()


def inside(path: Path, base: Path) -> bool:
    """True when the resolved `path` is `base` or below it (`base` already resolved)."""
    return path == base or path.is_relative_to(base)


SLUG_MAX = 40


def slug(name: str, max_len: int | None = SLUG_MAX) -> str:
    """Lowercase ASCII letters and digits; every other run of characters becomes one `-`; no leading or trailing
    `-`; at most `max_len` characters (None: no limit). Empty when `name` has no letter or digit."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return s[:max_len].rstrip("-") if max_len is not None else s


def safe_name(name: str, default: str = "ref") -> str:
    """The last path component of `name` with every character other than letters, digits, `.`, `_` and `-`
    replaced by `-`, without leading dots or dashes; `default` when nothing remains."""
    base = re.split(r"[\\/]", name)[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).lstrip(".-")[:120]
    return base or default


# Image types accepted in data URLs, with the file suffixes each may carry (the first is used when a name has none).
IMAGE_SUFFIXES = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
}


def decode_data_url(value: object, allowed: tuple[str, ...] | None) -> tuple[str, bytes]:
    """`(mime type, bytes)` of a base64 data URL whose type is in `allowed` (None: any type); 400 otherwise."""
    if not isinstance(value, str) or not value.startswith("data:") or "," not in value:
        raise HttpError(400, "expected a data URL")
    header, payload = value[5:].split(",", 1)
    parts = header.split(";")
    mime = parts[0].strip().lower()
    if "base64" not in parts[1:]:
        raise HttpError(400, "the data URL must be base64")
    if allowed is not None and mime not in allowed:
        raise HttpError(400, f"data URL type {mime or '(none)'} is not one of {', '.join(allowed)}")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HttpError(400, "the data URL is not valid base64") from None
    if not data:
        raise HttpError(400, "the data URL is empty")
    return mime, data


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int] | None:
    """`(width, height)` from the IHDR chunk of PNG bytes (the first 24 suffice); None when they are not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def write_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` through a temporary file in the same directory, so a reader sees the old or the new
    file. A symbolic link at `path` is replaced, never followed."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_new(directory: Path, name: str, data: bytes, numbered: bool = False) -> Path:
    """Write `data` to `directory/name`, or to `<stem>-2<suffix>`, `-3`, ... when the name is taken; with
    `numbered`, to the first free `<stem>-1<suffix>`, `-2`, ... Never overwrites and never follows a link at the
    target."""
    stem, suffix = os.path.splitext(name)
    n = 1
    while True:
        target = directory / (name if n == 1 and not numbered else f"{stem}-{n}{suffix}")
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            n += 1
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return target
