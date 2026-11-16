"""Per-scene report: which scenes need a new voice recording or a new render.

A narrated scene needs a voice recording when it has no voice version, or the
latest one does not match the storyboard (`narration.recording_problems`: its
sentences, or the resolved voice of a sentence). It needs a render when it has
no rendered version, a newer version is scaffolded and not rendered, the
render used another voice version than the latest, or what `scaffold` copied
into the rendered version differs from what it would copy now: the image
(`background.png`), `brief.md` (the brief, the On screen text, the image name,
the frame size; for a manim or video scene also its engine's section), for a template
scene `card.js`, for a presenter scene the recording (`speech_sha256` of meta.json), and for a video scene the ambience level (`video_scene.ambience_level`: the
scene's `ambience` or `mix.ambience_relative_db` changed). A clip scene needs a new import when `storyboard.clip_problem`
names one. A scene of a shared world is judged with its world
(`world.render_reasons`): a newer world version, or a change of the world's
scenes, voice versions, lengths, Briefs or On screen text, makes every scene of
the world stale. A new voice version makes the render stale only once it is
imported, so the two are reported separately.

An HTML scene plays from its page, and the film's default form is the HTML
film (`html`), so an HTML scene is judged on its latest page version, not on
its render. A scaffolded page with no render, or newer than the render, is
current when it matches the storyboard. A plain HTML scene with no page needs
`scaffold` ("no page version"); a world scene is judged on its latest world
version (`world.page_reasons`). `rendered` says whether that page version
has a render, for a film MP4 (`assemble`).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import manim_scene, narration, pages, presenter_scene, scenes, state, storyboard, video_scene, world
from .engine import Engine


def voice_reasons(project: Path, data: dict, scene: dict) -> list[str]:
    """Why the scene needs a new voice recording; empty if it does not."""
    if not storyboard.narrated(scene):
        return []
    vdir = state.latest_voice(project, scene["id"])
    if vdir is None:
        return ["no voice version"]
    return narration.recording_problems(data, scene, vdir)


BRIEFS = {Engine.MANIM: manim_scene.manim_brief, Engine.VIDEO: video_scene.video_brief,
          Engine.PRESENTER: presenter_scene.presenter_brief}


def render_reasons(project: Path, scene: dict, data: dict | None = None) -> list[str]:
    """Why the scene needs a new render (a clip scene: a new import); empty if it does not. A world scene needs
    the storyboard `data`."""
    sid = scene["id"]
    if storyboard.world_name(scene) and data is not None:
        return world.page_reasons(project, data, scene)
    if storyboard.is_clip(scene):
        problem = storyboard.clip_problem(project, scene)
        return [problem] if problem else []
    sdir = state.latest_render(project, sid)
    page = pages.latest_page(project, sid) if pages.is_page_scene(scene) else None
    out = []
    if page is not None and page != sdir:
        sdir = page  # an HTML scene is judged on its latest page
        meta = {"voice_version": _read(page / "voice_version").strip() or None}
    elif sdir is None:
        return ["no page version; run scaffold" if pages.is_page_scene(scene) else "no rendered version"]
    else:
        latest = state.latest_scene(project, sid)
        if latest != sdir:
            out.append(f"version {latest.name} is scaffolded and not rendered")
        meta = state.read_meta(sdir) or {}
    rendered = meta.get("engine") or Engine.HTML
    if rendered != Engine.of(scene):
        return out + [f"rendered as engine {rendered}, the storyboard has {Engine.of(scene)}"]
    voice = state.latest_voice(project, sid) if storyboard.narrated(scene) else None
    if voice is not None and meta.get("voice_version") != voice.name:
        out.append(f"rendered with voice {meta.get('voice_version')}, the latest voice version is {voice.name}")
    background = sdir / scenes.BACKGROUND
    image = storyboard.image_path(project, scene["image"]) if scene.get("image") else None
    if image is None and background.is_file():
        out.append("rendered with an image, the storyboard has none")
    elif image is not None and image.is_file() and (
            not background.is_file() or background.read_bytes() != image.read_bytes()):
        out.append(f"the image {scene['image']} differs from the one rendered")
    if not (sdir / "timing.json").is_file():
        return out + ["the rendered version has no timing.json (a world scene's cut); run `scaffold` again"]
    timing = json.loads((sdir / "timing.json").read_text(encoding="utf-8"))
    if timing.get("estimated"):
        out.append("the page is timed from an estimate of its words; record the voice and run scaffold again")
    vfile = sdir / "voice_version"
    vname = vfile.read_text().strip() if vfile.is_file() else None
    brief = BRIEFS.get(Engine.of(scene), scenes.brief_markdown)(scene, timing, vname)
    if _read(sdir / "brief.md") != brief:
        out.append("brief.md differs from the storyboard (brief, On screen text, image name or frame size)")
    model_clip = sdir / video_scene.MODEL_MP4
    if storyboard.is_video(scene) and model_clip.is_file() and \
            meta.get("ambience_relative_db") != (level := video_scene.ambience_level(scene, model_clip)):
        out.append(f"rendered with ambience level {meta.get('ambience_relative_db')} LU, the storyboard and settings "
                   f"give {level}")
    if storyboard.is_presenter(scene) and voice is not None and meta.get("voice_version") == voice.name and \
            (speech := voice / presenter_scene.NARRATION).is_file() and \
            meta.get("speech_sha256") != presenter_scene.speech_digest(speech):
        out.append(f"the recording {voice.name}/{presenter_scene.NARRATION} differs from the one the presenter spoke")
    if scene.get("template") and _card(_read(sdir / scenes.CARD_JS)) != _card(scenes.card_js(scene)):
        out.append("card.js differs from the storyboard (On screen text or author)")
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _card(text: str) -> str:
    """`card.js` without its comment line."""
    return text.partition("\n")[2]


def rendered(project: Path, scene: dict) -> bool:
    """The scene's current version has a render: for an HTML scene its latest page version (a world scene: the
    latest world version) has one; for any other scene a render exists."""
    sdir = state.latest_render(project, scene["id"])
    if sdir is None:
        return False
    if name := storyboard.world_name(scene):
        latest = world.latest_world(project, name)
        return latest is not None and (state.read_meta(sdir) or {}).get("world_version") == latest.name
    if pages.is_page_scene(scene):
        return pages.latest_page(project, scene["id"]) in (None, sdir)
    return True


def report(project: Path, data: dict) -> dict:
    """`{"scenes": [...]}`, one entry per scene in storyboard order (fields in
    `references/storyboard.md`, "Scene status")."""
    out = []
    for s in storyboard.scenes(data):
        voice = state.latest_voice(project, s["id"])
        render = state.latest_render(project, s["id"])
        v, r = voice_reasons(project, data, s), render_reasons(project, s, data)
        out.append({"id": s["id"], "narrated": storyboard.narrated(s),
                    "voice_version": voice.name if voice else None, "needs_voice": bool(v), "voice_reasons": v,
                    "scene_version": render.name if render else None, "needs_render": bool(r),
                    "render_reasons": r, "rendered": rendered(project, s)})
    return {"scenes": out}
