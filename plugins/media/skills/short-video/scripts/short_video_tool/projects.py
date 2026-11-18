"""A new film project (`init`): its directories, settings.yaml, storyboard template, images and source text."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import settings, storyboard

LAYOUT = ("images", "sources", "voice", "scenes", "music", "film")


class ProjectError(Exception):
    """A project cannot be created: the path is taken, or an input is missing."""


@dataclass(frozen=True)
class Created:
    """A created project: its directory, the storyboard file name and the copied PNGs (file names in images/)."""

    project: Path
    storyboard_file: str
    images: list[str]


def create(project: Path, images: Path | None = None, source: Path | None = None, as_json: bool = False,
           silent: bool = False, length: float | None = None) -> Created:
    """Create the project at `project` (missing or empty): the `LAYOUT` directories, settings.yaml copied from
    the skill defaults (with `length` as the film length when given), lessons.md, the PNGs of `images`, the
    `source` text file in sources/, and storyboard.md (storyboard.json with `as_json`), silent with `silent`.
    Selects the project's settings (`settings.use_project`). Raises ProjectError for a taken path, a folder
    without PNGs or a missing source file, and StoryboardError when the written storyboard does not load."""
    if project.exists() and not project.is_dir():
        raise ProjectError(f"{project} exists and is not a directory")
    if project.exists() and any(project.iterdir()):
        raise ProjectError(f"{project} already exists and is not empty")
    pngs = []
    if images is not None:
        pngs = sorted(p for p in images.iterdir() if p.is_file() and p.suffix.lower() == ".png") if images.is_dir() else []
        if not pngs:
            raise ProjectError(f"no PNG files in {images}")
    for d in LAYOUT:
        (project / d).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(settings.SETTINGS_FILE, project / settings.PROJECT_FILE)
    settings.use_project(project)
    for p in pngs:
        shutil.copyfile(p, project / "images" / p.name)
    if source is not None:
        if not source.is_file():
            raise ProjectError(f"source file {source} not found")
        shutil.copyfile(source, project / "sources" / source.name)
    lessons = project / "lessons.md"
    if not lessons.exists():
        lessons.write_text(settings.asset("lessons.md"), encoding="utf-8")
    title = project.name.replace("-", " ").replace("_", " ").capitalize()
    name, make = (storyboard.JSON_FILE, storyboard.json_template) if as_json else (storyboard.MD_FILE, storyboard.template)
    if length is not None:
        settings.set_length(project / settings.PROJECT_FILE, length)
    (project / name).write_text(make(title, [p.name for p in pngs], silent, length), encoding="utf-8")
    storyboard.load(project)
    return Created(project, name, [p.name for p in pngs])
