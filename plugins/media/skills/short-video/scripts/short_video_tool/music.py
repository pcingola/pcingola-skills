"""Music versions, imported from `music.file`.

The agent makes the track with the music skill (or the user supplies one) and
sets `music.file`; `music` copies it into the next `music/v<N>/`. When the
file has the music skill's sidecars (`<file>.json`, `<file>.txt`), the first
is merged into `meta.json` and the second copied to `lyrics.txt`.
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import settings, state, storyboard, versions


def music_root(project: Path) -> Path:
    return project / "music"


def target_seconds(voice_durations: list[float]) -> int:
    return int(math.ceil(sum(voice_durations) + settings.get()["music"]["extra_seconds"]))


def voice_durations(project: Path, data: dict) -> list[float]:
    """The length of each scene with a voice version: its narration, or its
    imported clip when that is longer (a narrated clip scene)."""
    out = []
    for s in storyboard.scenes(data):
        vdir = state.latest_voice(project, s["id"])
        if vdir is not None and storyboard.narrated(s):
            narration = json.loads((vdir / "timing.json").read_text(encoding="utf-8"))["duration"]
            out.append(storyboard.with_clip(s, project, narration))
    return out


def clip_durations(project: Path, data: dict) -> list[float]:
    """The length of each silent scene: a clip scene without narration that has an imported clip, or an HTML
    scene's `length`."""
    found = (storyboard.length_seconds(s) if storyboard.length_seconds(s) is not None
             else storyboard.clip_seconds(project, s)
             for s in storyboard.scenes(data) if not storyboard.narrated(s))
    return [t for t in found if t is not None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def import_file(project: Path, src: Path) -> Path:
    if not src.is_file():
        raise FileNotFoundError(src)
    out = versions.next_version(music_root(project))
    dest = out / f"music{src.suffix.lower()}"
    shutil.copyfile(src, dest)
    meta = {"source": "file", "file": dest.name, "original": src.name, "created_at": _now()}
    side = src.with_name(src.name + ".json")
    if side.is_file():
        meta = {**json.loads(side.read_text(encoding="utf-8")), **meta}
    texts = src.with_name(src.name + ".txt")
    if texts.is_file():
        shutil.copyfile(texts, out / "lyrics.txt")
    state.write_meta(out, meta)
    return dest


def music_file(version_dir: Path) -> Path:
    meta = state.read_meta(version_dir)
    if not meta or not (version_dir / meta["file"]).is_file():
        raise FileNotFoundError(f"{version_dir} holds no music file")
    return version_dir / meta["file"]
