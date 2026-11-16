"""The page an HTML scene plays from, rendered or not.

A plain HTML scene plays from its latest scene version that holds an
`index.html` (or the version named), in scene time. A scene of a shared world
plays from the latest world version (or the world version named), from its
start in `world.json`. `stills`, `check` and `html` work on these pages, so an
HTML scene needs no render.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import scenes, state, storyboard, versions, world
from .engine import Engine
from .scenes import SceneError

INDEX = "index.html"


@dataclass(frozen=True)
class Page:
    """A scene's page: the version directory holding `index.html`, the scene's start and length in page time,
    and the world it belongs to (None for a plain scene)."""

    dir: Path
    start: float
    duration: float
    world: str | None = None


def is_page_scene(scene: dict) -> bool:
    """An HTML scene: it plays from a page (not manim, video, presenter or clip)."""
    return Engine.of(scene) == Engine.HTML


def root_duration(html: str) -> float | None:
    """`data-duration` of the page's root (the element with `data-composition-id`), or None."""
    _, tag = scenes.composition_root(html)
    m = re.search(r'\bdata-duration\s*=\s*["\']([0-9.]+)["\']', tag)
    return float(m.group(1)) if m else None


def latest_page(project: Path, scene_id: str) -> Path | None:
    """The latest scene version with an `index.html`, or None."""
    return versions.latest_version(state.scene_root(project, scene_id), require=INDEX)


def scene_page(project: Path, data: dict, scene: dict, version: str | None = None) -> Page:
    """The page of an HTML scene. `version` names a scene version (a world scene: a world version). SceneError
    when the scene is not an HTML scene or has no page yet."""
    sid = scene["id"]
    if not is_page_scene(scene):
        raise SceneError(f"scene {sid} is a {Engine.of(scene)} scene: it has no page; use `frames` on its render")
    if name := storyboard.world_name(scene):
        root = world.world_root(project, name)
        wdir = root / version if version else world.latest_world(project, name)
        if wdir is None or not (wdir / INDEX).is_file():
            raise SceneError(f"world {name}: no {'version ' + version if version else 'version'} with "
                             f"{INDEX}; run `scaffold --scene {sid}` first")
        plan = json.loads((wdir / world.WORLD_JSON).read_text(encoding="utf-8"))
        span = next((s for s in plan["scenes"] if s["id"] == sid), None)
        if span is None:
            raise SceneError(f"world {name} {wdir.name} has no scene {sid}; run `scaffold --scene {sid}` again")
        return Page(wdir, float(span["start"]), float(span["duration"]), name)
    sdir = state.scene_root(project, sid) / version if version else latest_page(project, sid)
    if sdir is None or not (sdir / INDEX).is_file():
        raise SceneError(f"scene {sid}: no {'version ' + version if version else 'version'} with {INDEX}; "
                         "run `scaffold` first")
    duration = root_duration((sdir / INDEX).read_text(encoding="utf-8"))
    if duration is None:
        raise SceneError(f"{sdir / INDEX}: the root has no numeric data-duration")
    return Page(sdir, 0.0, duration)


def check(project: Path, data: dict, scene: dict, node_dir: Path) -> tuple[Path, list[str]]:
    """The static checks `render` runs, on the scene's latest page (a world scene: its world's), without
    rendering. Returns (the page's index.html, lint warnings); SceneError on an error."""
    page = scene_page(project, data, scene)
    timing = json.loads((page.dir / "timing.json").read_text(encoding="utf-8"))
    if page.world:
        plan = json.loads((page.dir / world.WORLD_JSON).read_text(encoding="utf-8"))
        warnings = scenes.check_page(page.dir, node_dir, timing, float(plan["duration"]))
    else:
        html = (page.dir / INDEX).read_text(encoding="utf-8")
        warnings = scenes.check_page(page.dir, node_dir, timing, scenes.scene_duration(scene, timing["duration"]),
                                     scenes.check_background(page.dir, html, scene))
    return page.dir / INDEX, warnings
