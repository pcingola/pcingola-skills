"""The animation folder the server serves, and the check that keeps every served path inside it."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

from .http_error import HttpError

VERSION_DIR = re.compile(r"^v(\d+)$")


class AnimationFolder:
    """One animation folder (`animation.json`, `index.html`, `chapters/`, `comments.json`, `marks/`, `v<N>/`)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"not a directory: {self.root}")

    @property
    def index(self) -> Path:
        return self.root / "index.html"

    @property
    def comments_file(self) -> Path:
        return self.root / "comments.json"

    @property
    def marks_dir(self) -> Path:
        return self.root / "marks"

    def resolve(self, url_path: str) -> Path:
        """The file that `url_path` (the part of the URL path after `/anim/`, percent-encoded, no query) names.

        403 when it is empty, holds a NUL or a backslash, is absolute after decoding, has a `..` segment, or
        resolves (symbolic links followed) to a path outside the folder. Decoding is applied once, as a browser
        encodes once; a doubly encoded `..` stays a literal name inside the folder."""
        try:
            decoded = unquote(url_path, errors="strict")
        except UnicodeDecodeError:
            raise HttpError(403, "path refused") from None
        if not decoded or "\0" in decoded or "\\" in decoded:
            raise HttpError(403, "path refused")
        if decoded.startswith("/") or re.match(r"^[A-Za-z]:", decoded):
            raise HttpError(403, "absolute path refused")
        if any(part == ".." for part in decoded.split("/")):
            raise HttpError(403, "path outside the animation folder")
        path = (self.root / decoded).resolve()
        if path != self.root and not path.is_relative_to(self.root):
            raise HttpError(403, "path outside the animation folder")
        return path

    def url_of(self, path: str | Path) -> str | None:
        """`/anim/<relative path>` of a file inside the folder; None for a file outside it."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_relative_to(self.root):
            return None
        return "/anim/" + resolved.relative_to(self.root).as_posix()

    def animation(self) -> dict | None:
        """The parsed `animation.json`, None when it is missing or not valid JSON."""
        try:
            value = json.loads((self.root / "animation.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def version(self) -> int:
        """The highest N of the `v<N>/` snapshot folders, 0 when there is none."""
        numbers = [int(m.group(1)) for p in self.root.iterdir() if p.is_dir() and (m := VERSION_DIR.match(p.name))]
        return max(numbers, default=0)

    def index_mtime(self) -> float | None:
        try:
            return self.index.stat().st_mtime
        except OSError:
            return None
