"""The projects root: `<root>/<directory of a kind>/<project>/` with a `project.json`."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from .deck import ASSEMBLY, SLIDE_DIR, VERSION_JSON, deck_details, slide_count, versions_of
from .paths import HttpError, inside, read_json, resolve_abs, slug, write_atomic


class Kind(NamedTuple):
    """A kind of project, one entry of the page's left column: its projects live in `<root>/<directory>/` and its
    requests go to the workspace skill `studio:<skill>`. `ready` is false for kinds whose phase is not done."""
    id: str
    label: str
    directory: str
    skill: str
    ready: bool


KINDS = (
    Kind("image", "Images", "images", "images", True),
    Kind("infographic", "Infographics", "infographics", "images", True),
    Kind("slide", "Slides", "slides", "images", True),
    Kind("short-video", "Short videos", "short-video", "short-video", False),
)
KIND_BY_ID = {k.id: k for k in KINDS}
KIND_BY_DIRECTORY = {k.directory: k for k in KINDS}


def kind_named(value: object) -> Kind:
    """The kind whose id is `value`; 400 otherwise."""
    if not isinstance(value, str) or value not in KIND_BY_ID:
        raise HttpError(400, f"kind must be one of {', '.join(KIND_BY_ID)}")
    return KIND_BY_ID[value]


PROJECT_FILE = "project.json"
# Values of `autonomy` in project.json; the first is the default of a new project.
AUTONOMY = ("step", "auto")


def prepare_root(root: Path) -> Path:
    """Create the root and every kind's directory when missing; return the resolved root."""
    root = Path(root).expanduser()
    for kind in KINDS:
        (root / kind.directory).mkdir(parents=True, exist_ok=True)
    return root.resolve()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


# Subdirectories of a project whose files are watched besides its top level; a deck's `slide-<k>/` directories
# and their `marks/` are watched too.
WATCHED_SUBDIRS = ("refs", "marks")


def _slide_subdirs(directory: Path) -> list[str]:
    """`slide-<k>` and `slide-<k>/marks` for each slide directory at the top level of a project, links not
    followed."""
    try:
        with os.scandir(directory) as it:
            names = sorted(e.name for e in it if SLIDE_DIR.match(e.name) and e.is_dir(follow_symlinks=False))
    except OSError:
        return []
    return [rel for name in names for rel in (name, os.path.join(name, "marks"))]


def files_of(directory: Path) -> dict[str, tuple[int, int]]:
    """`{relative path: (mtime_ns, size)}` of the files at the top level of a project, in its WATCHED_SUBDIRS and in
    each `slide-<k>/` and `slide-<k>/marks/`, links not followed."""
    out: dict[str, tuple[int, int]] = {}
    for rel in ("", *WATCHED_SUBDIRS, *_slide_subdirs(directory)):
        try:
            with os.scandir(directory / rel) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            out[os.path.join(rel, entry.name)] = (st.st_mtime_ns, st.st_size)
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def project_dirs(root: Path, kind: Kind) -> list[Path]:
    """The project directories of `kind`: subdirectories of `<root>/<directory>` holding a project.json."""
    base = root / kind.directory
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []
    return [p for p in entries if p.is_dir() and not p.is_symlink() and (p / PROJECT_FILE).is_file()]


def _complete_versions(files: dict[str, tuple[int, int]], rel: str = "") -> int:
    """The complete versions (v<N>.png with v<N>.json) among `files` directly in the subdirectory `rel`."""
    names = {os.path.basename(f) for f in files if os.path.dirname(f) == rel}
    return sum(1 for f in names if VERSION_JSON.match(f) and f"{f[:-5]}.png" in names)


def list_projects(root: Path, kind: Kind) -> list[dict]:
    """`[{"dir", "name", "brief", "updated", "versions"}]`, newest first; `versions` counts complete versions
    (v<N>.png with v<N>.json), for a deck those of its slides, and a deck also has `slides`, its number of slides;
    `updated` is the latest change of a file files_of sees in the project."""
    out = []
    for p in project_dirs(root, kind):
        meta = read_json(p / PROJECT_FILE)
        meta = meta if isinstance(meta, dict) else {}
        files = files_of(p)
        stamps = [m for m, _ in files.values()]
        updated = max(stamps) / 1e9 if stamps else p.stat().st_mtime
        entry = {
            "dir": str(p),
            "name": meta.get("name") if isinstance(meta.get("name"), str) else p.name,
            "brief": meta.get("brief") if isinstance(meta.get("brief"), str) else "",
            "updated": iso(updated),
            "_t": updated,
        }
        if kind.id == "slide":
            n = slide_count(p)
            entry["versions"] = sum(_complete_versions(files, f"slide-{k}") for k in range(1, n + 1))
            entry["slides"] = n
        else:
            entry["versions"] = _complete_versions(files)
        out.append(entry)
    out.sort(key=lambda e: e["_t"], reverse=True)
    for e in out:
        del e["_t"]
    return out


def project_path(root: Path, value: object, kind: Kind | None = None, exists: bool = True) -> Path:
    """The resolved project directory `value`: `<root>/<directory of a kind>/<name>` (of `kind` when given). With
    `exists`, it must be a directory; 400 for a value that is not such a path, 404 when it does not exist."""
    p = resolve_abs(value, "project")
    if not inside(p, root) or p.parent.parent != root or p.parent.name not in KIND_BY_DIRECTORY:
        raise HttpError(400, "project must be a project directory <root>/<directory of a kind>/<project> inside the "
                             "projects root")
    if kind is not None and p.parent.name != kind.directory:
        raise HttpError(400, f"project is not a {kind.id} project (<root>/{kind.directory}/<project>)")
    if exists and not p.is_dir():
        raise HttpError(404, f"no project directory {p}")
    return p


def is_deck(project: Path) -> bool:
    """True for a project of kind `slide`, a deck."""
    return project.parent.name == KIND_BY_ID["slide"].directory


def project_details(root: Path, value: object) -> dict:
    """`{"dir", "project", "versions", "refs"}` of a project, plus `deck` (deck_details) for a deck, whose own
    `versions` is empty; 404 without project.json."""
    p = project_path(root, value)
    meta = read_json(p / PROJECT_FILE)
    if meta is None:
        raise HttpError(404, f"no readable {PROJECT_FILE} in {p}")
    refs_dir = p / "refs"
    refs = sorted(str(f) for f in refs_dir.iterdir() if f.is_file() and not f.name.startswith(".")) \
        if refs_dir.is_dir() else []
    if is_deck(p):
        return {"dir": str(p), "project": meta, "versions": [], "refs": refs, "deck": deck_details(p, meta)}
    return {"dir": str(p), "project": meta, "versions": versions_of(p), "refs": refs}


def write_project_json(project: Path, meta: dict) -> None:
    write_atomic(project / PROJECT_FILE, (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode())


# Held across each read, change and write of a project.json by the server, so two requests at once (two quick
# /api/chosen calls) do not lose one change.
_project_lock = threading.Lock()


def update_project(project: Path, update) -> dict:
    """Read project.json, apply `update(meta)` (which changes the dict in place, or returns False to change nothing)
    and replace the file atomically, under one lock; returns the contents. 404 when project.json is missing or not an
    object."""
    with _project_lock:
        meta = read_json(project / PROJECT_FILE)
        if not isinstance(meta, dict):
            raise HttpError(404, f"no readable {PROJECT_FILE} in {project}")
        if update(meta) is not False:
            write_project_json(project, meta)
        return meta


NAME_WORDS = 6
UNTITLED = "Untitled"


def project_name(brief: str) -> str:
    """The first NAME_WORDS words of `brief` that give a slug of at most SLUG_MAX characters; UNTITLED when
    the brief has no letter or digit."""
    words = brief.split()[:NAME_WORDS]
    while len(words) > 1 and slug(" ".join(words)) != slug(" ".join(words), max_len=None):
        words.pop()
    name = " ".join(words)
    return name if slug(name) else UNTITLED


def create_project(root: Path, kind: Kind, brief: str, created: str, autonomy: str = AUTONOMY[0]) -> Path:
    """A new project `<root>/<directory of kind>/<slug of the brief's first words>` (`-2`, `-3` when taken) with its
    project.json, `kind` and `autonomy` in it (a deck also `assembly` and `chosen`). The directory is made with mkdir, which fails when it exists, so two requests at once never get
    the same directory."""
    name = project_name(brief)
    base = slug(name)
    n = 1
    while True:
        p = root / kind.directory / (base if n == 1 else f"{base}-{n}")
        try:
            p.mkdir()
            break
        except FileExistsError:
            n += 1
    meta = {"name": name, "brief": brief, "kind": kind.id, "created": created, "autonomy": autonomy, "settings": {}}
    if kind.id == "slide":
        meta |= {"assembly": ASSEMBLY[0], "chosen": {}}
    write_project_json(p, meta)
    return p


def name_untitled(project: Path, brief: str) -> None:
    """Give an untitled project with no brief (made by `/api/new`) the name and brief of its first `generate`. The
    directory keeps its name."""
    def name(meta: dict) -> bool:
        if meta.get("name") != UNTITLED or meta.get("brief"):
            return False
        meta |= {"name": project_name(brief), "brief": brief}
        return True
    try:
        update_project(project, name)
    except HttpError:
        pass  # no readable project.json: nothing to name


def subdir(project: Path, name: str) -> Path:
    """`<project>/<name>`, created when missing; 400 when it resolves outside the project (a link)."""
    d = project / name
    d.mkdir(exist_ok=True)
    if not inside(d.resolve(), project) or not d.resolve().is_dir():
        raise HttpError(400, f"{d} is not a directory inside the project")
    return d.resolve()
