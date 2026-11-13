"""`meta.json` files and the voice and scene version directories of a project.

A version is complete once its `meta.json` is written: `voice` writes it after
synthesis, `render` after the scene is rendered.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import versions

META = "meta.json"


def read_meta(version_dir: Path) -> dict | None:
    p = version_dir / META
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def write_meta(version_dir: Path, meta: dict) -> Path:
    p = version_dir / META
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def voice_root(project: Path, scene_id: str) -> Path:
    return project / "voice" / scene_id


def scene_root(project: Path, scene_id: str) -> Path:
    return project / "scenes" / scene_id


def latest_voice(project: Path, scene_id: str) -> Path | None:
    """Latest complete voice version (one whose meta.json was written)."""
    return versions.latest_version(voice_root(project, scene_id), require=META)


def latest_scene(project: Path, scene_id: str) -> Path | None:
    """Latest scene version, rendered or not."""
    return versions.latest_version(scene_root(project, scene_id))


def latest_render(project: Path, scene_id: str) -> Path | None:
    """Latest rendered scene version (one whose meta.json was written)."""
    return versions.latest_version(scene_root(project, scene_id), require=META)
