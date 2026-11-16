"""Shared worlds: consecutive HTML scenes cut from one page.

The scenes of the storyboard with the same `world` (`World:` in
storyboard.md) share one HyperFrames page, `worlds/<name>/v<N>/index.html`,
whose root has `data-composition-id=<name>` and whose timeline is
`window.__timelines["<name>"]`. The camera and the light run on across the
scenes without a cut.

Times: scene k lasts `d_k`, its narration plus the template hold
(`scenes.scene_duration`), or its `length` when silent. Starts are
frame-aligned: `f_0 = 0`, `f_{k+1} = round((d_0 + ... + d_k) * fps)`,
`start_k = f_k / fps`; the world lasts `f_n / fps`.

`scaffold` writes the next world version: `index.html` (from the previous
version, its full length rewritten, or from `assets/world.html`), `timing.js`
(`window.TIMING = {duration, scenes: [{id, start, end, sentences}]}` with
absolute times, and the helpers `ST`, `STE`, `S`, `SE`, `W`, `WE`, each
taking the scene id first), `timing.json` (that structure), `world.json`
(`WorldPlan.to_dict`), the library and kit files the page loads (`scenes.copy_page_files`) and `brief.md`.

`render` checks and renders the latest world version once to `silent.mp4`,
then cuts it per scene into the next version of each scene,
`scenes/<id>/v<M>/`, with `world.json` (`world`, `version`, `start`,
`duration`), and muxes that scene's narration (or silence) with
`scenes.finish`. Every scene of the world gets a new version on every render.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import media, scenes, settings, state, storyboard, versions
from .scenes import SceneError

WORLD_JSON = "world.json"
PAGE = "world"


def world_root(project: Path, name: str) -> Path:
    return project / "worlds" / name


def latest_world(project: Path, name: str) -> Path | None:
    """Latest world version, rendered or not."""
    return versions.latest_version(world_root(project, name))


def latest_world_render(project: Path, name: str) -> Path | None:
    """Latest rendered world version (one whose meta.json was written)."""
    return versions.latest_version(world_root(project, name), require=state.META)


def seconds_attr(frames: int, fps: int) -> str:
    """`frames / fps` as an HTML attribute value precise enough that HyperFrames renders exactly `frames`
    frames (it rounds a length within 0.001 frame of a whole frame count, else rounds up)."""
    return f"{frames / fps:.6f}".rstrip("0").rstrip(".")


@dataclass
class WorldSpan:
    """One scene of a world: its frames `[start_frame, end_frame)` and the voice version it is timed to."""

    id: str
    start_frame: int
    end_frame: int
    voice_version: str | None

    def start(self, fps: int) -> float:
        return self.start_frame / fps

    def duration(self, fps: int) -> float:
        return (self.end_frame - self.start_frame) / fps

    def to_dict(self, fps: int) -> dict:
        return {"id": self.id, "start": round(self.start(fps), 6), "duration": round(self.duration(fps), 6),
                "frames": [self.start_frame, self.end_frame], "voice_version": self.voice_version}


@dataclass
class WorldPlan:
    """The frame-aligned layout of a world's scenes."""

    world: str
    fps: int
    spans: list[WorldSpan]

    @property
    def frames(self) -> int:
        return self.spans[-1].end_frame

    @property
    def duration(self) -> float:
        return self.frames / self.fps

    def to_dict(self) -> dict:
        return {"world": self.world, "duration": round(self.duration, 6), "fps": self.fps,
                "scenes": [s.to_dict(self.fps) for s in self.spans]}

    @classmethod
    def from_dict(cls, d: dict) -> WorldPlan:
        return cls(d["world"], d["fps"], [WorldSpan(s["id"], s["frames"][0], s["frames"][1], s["voice_version"])
                                         for s in d["scenes"]])


def frame_starts(durations: list[float], fps: int) -> list[int]:
    """`f_0 .. f_n`: `f_0 = 0`, `f_{k+1} = round((d_0 + ... + d_k) * fps)`."""
    out, total = [0], 0.0
    for d in durations:
        total += d
        out.append(round(total * fps))
    return out


def plan(project: Path, data: dict, name: str) -> tuple[WorldPlan, dict]:
    """The world's layout from the scenes' latest voice versions (or `length`), and its timing structure
    `{duration, scenes: [{id, start, end, sentences}]}` with absolute sentence and word times."""
    members = storyboard.world_scenes(data, name)
    if not members:
        raise SceneError(f"no scene has `World: {name}`")
    fps = settings.get()["video"]["fps"]
    timed = []
    for s in members:
        vdir, timing = scenes.scene_timing(project, s)
        timed.append((s, vdir, timing, scenes.scene_duration(s, timing["duration"])))
    f = frame_starts([d for *_, d in timed], fps)
    spans = [WorldSpan(s["id"], f[k], f[k + 1], vdir.name if vdir else None)
             for k, (s, vdir, _, _) in enumerate(timed)]
    p = WorldPlan(name, fps, spans)
    timing = {"duration": p.duration, "scenes": [
        {"id": span.id, "start": span.start(fps), "end": span.start(fps) + span.duration(fps),
         "sentences": [shift_sentence(x, span.start(fps)) for x in t["sentences"]]}
        for span, (_, _, t, _) in zip(spans, timed)]}
    return p, timing


def shift_sentence(sentence: dict, offset: float) -> dict:
    """A timing.json sentence with its start, end and word times moved by `offset` seconds."""
    def at(t: float) -> float:
        return round(t + offset, 6)

    return {"index": sentence["index"], "text": sentence["text"], "start": at(sentence["start"]),
            "end": at(sentence["end"]),
            "words": [{"text": w["text"], "start": at(w["start"]), "end": at(w["end"])}
                      for w in sentence.get("words", [])]}


def timing_js(timing: dict, source: str = "") -> str:
    """`timing.js` of a world page: `window.TIMING` with every scene's absolute times, plus the helpers."""
    header = f"// Generated by short-video scaffold{' from ' + source if source else ''}. Do not edit.\n"
    return (header + "window.TIMING = " + json.dumps(timing, indent=1, ensure_ascii=False) + ";\n"
            + settings.asset("timing-helpers.js"))


def brief_markdown(data: dict, p: WorldPlan, timing: dict) -> str:
    """`brief.md` of a world version: each scene's Brief, start, end and sentences in world time."""
    v = settings.get()["video"]
    lines = [f"# World `{p.world}`", "",
             f"- Scenes: {', '.join(s.id for s in p.spans)}",
             f"- Composition: {v['width']}x{v['height']}, {v['fps']} fps, id `{p.world}`, "
             f"{p.duration:.3f} s ({p.frames} frames)",
             "- Times are world times. Helpers take the scene id first: ST(\"id\"), STE(\"id\"), S(\"id\", n), "
             "SE(\"id\", n), W(\"id\", n, \"word\"), WE(\"id\", n, \"word\").", ""]
    for span, t in zip(p.spans, timing["scenes"]):
        scene = storyboard.scene_by_id(data, span.id)
        narration = f"voice {span.voice_version}" if span.voice_version else "none (silent)"
        lines += [f"## Scene `{span.id}`: ST={t['start']:.2f} to STE={t['end']:.2f}", "",
                  f"- Narration: {narration}", f"- Frames: {span.start_frame} to {span.end_frame}", "",
                  "### Brief", "", str(scene.get("brief") or "").strip() or "none", ""]
        beats = scene.get("beats") or []
        if t["sentences"]:
            lines += ["### Sentences and beats", ""]
        for x in t["sentences"]:
            i = x["index"]
            lines.append(f"{i}. S(\"{span.id}\", {i})={x['start']:.2f} to SE(\"{span.id}\", {i})={x['end']:.2f}: "
                         f"\"{x['text']}\"")
            lines.append(f"   - Beat: {beats[i - 1] if i - 1 < len(beats) else ''}")
            if x["words"]:
                lines.append("   - Words: " + ", ".join(f"{w['text']} {w['start']:.2f}" for w in x["words"]))
        lines.append("")
    return "\n".join(lines)


def scaffold(project: Path, data: dict, name: str, node_dir: Path, refresh: bool = False) -> Path:
    """Create the next world version and return its directory. With `refresh`, rewrite the latest version's
    brief.md, timing files and world.json in place instead, keeping its page and the author's files."""
    scenes.gsap_file(node_dir)
    p, timing = plan(project, data, name)
    previous = latest_world(project, name)
    out = (scenes.refresh_target(previous, f"world {name}") if refresh
           else versions.next_version(world_root(project, name)))
    length = seconds_attr(p.frames, p.fps)
    if previous is not None and (previous / "index.html").is_file():
        html = scenes.set_full_length((previous / "index.html").read_text(encoding="utf-8"), length)
    else:
        html = scenes.render_template(name, length, PAGE)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "timing.js").write_text(timing_js(timing, "the world's voice versions"), encoding="utf-8")
    (out / "timing.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / WORLD_JSON).write_text(json.dumps(p.to_dict(), indent=2) + "\n", encoding="utf-8")
    scenes.copy_page_files(out, html, node_dir)
    if previous is not None and previous != out:
        scenes.carry_author_files(previous, out)
    (out / "brief.md").write_text(brief_markdown(data, p, timing), encoding="utf-8")
    return out


def cut_filter(span: WorldSpan) -> str:
    """The `-vf` that takes frames `[start_frame, end_frame)` of the world's render."""
    return f"select='between(n,{span.start_frame},{span.end_frame - 1})',setpts=N/FRAME_RATE/TB"


def cut_scene(world_mp4: Path, span: WorldSpan, out: Path) -> Path:
    """Cut the scene's frames out of the world's `silent.mp4` into `out`, in the `encode:` codec."""
    e = settings.encode()
    media.run([media.which("ffmpeg"), "-y", "-v", "error", "-i", world_mp4, "-an", "-vf", cut_filter(span),
               "-r", str(settings.get()["video"]["fps"]),
               "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"], out])
    return out


def render(project: Path, data: dict, name: str, node_dir: Path) -> list[Path]:
    """Render the latest world version and write the next version of each of its scenes. Returns every
    scene.mp4, in film order."""
    wdir = latest_world(project, name)
    if wdir is None or not (wdir / "index.html").is_file():
        raise SceneError(f"world {name}: nothing to render; run `scaffold` on one of its scenes first")
    p = WorldPlan.from_dict(json.loads((wdir / WORLD_JSON).read_text(encoding="utf-8")))
    members = [s["id"] for s in storyboard.world_scenes(data, name)]
    if members != [s.id for s in p.spans]:
        raise SceneError(f"world {name}: version {wdir.name} has scenes {', '.join(s.id for s in p.spans)}, the "
                         f"storyboard has {', '.join(members)}; run `scaffold` again")
    timing = json.loads((wdir / "timing.json").read_text(encoding="utf-8"))
    audio = [scenes.voice_audio(project, span.id, span.voice_version) for span in p.spans]
    silent = scenes.render_page(wdir, node_dir, timing, p.duration)
    state.write_meta(wdir, {"world": name, "version": wdir.name, "duration": round(p.duration, 6),
                            "frames": p.frames, "fps": p.fps,
                            "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    out = []
    for span, (audio_input, voice_meta) in zip(p.spans, audio):
        sdir = versions.next_version(state.scene_root(project, span.id))
        start = round(span.start(p.fps), 6)
        (sdir / WORLD_JSON).write_text(json.dumps({"world": name, "version": wdir.name, "start": start,
                                                   "duration": round(span.duration(p.fps), 6)}, indent=2) + "\n",
                                       encoding="utf-8")
        cut = cut_scene(silent, span, sdir / "silent.mp4")
        out.append(scenes.finish(sdir, cut, audio_input, {"scene": span.id, **voice_meta, "world": name,
                                                          "world_version": wdir.name, "start": start}))
    return out


def page_reasons(project: Path, data: dict, scene: dict) -> list[str]:
    """Why a world scene needs a new world version (`scaffold`); empty if its latest world version matches the
    storyboard and the voice versions. The HTML film plays that version, rendered or not."""
    name = storyboard.world_name(scene)
    wdir = latest_world(project, name)
    if wdir is None or not (wdir / WORLD_JSON).is_file():
        return ["no world version; run scaffold"]
    try:
        p, timing = plan(project, data, name)
    except SceneError as e:
        return [str(e)]
    if json.loads((wdir / WORLD_JSON).read_text(encoding="utf-8")) != p.to_dict():
        return ["the world's scenes, voice versions or lengths changed; run `scaffold` again"]
    if (wdir / "brief.md").read_text(encoding="utf-8") != brief_markdown(data, p, timing):
        return ["the world's brief.md differs from the storyboard (a scene's Brief or On screen text)"]
    return []


def render_reasons(project: Path, data: dict, scene: dict) -> list[str]:
    """Why a world scene needs a new render; empty if it does not."""
    name = storyboard.world_name(scene)
    sdir = state.latest_render(project, scene["id"])
    if sdir is None:
        return ["no rendered version"]
    meta = state.read_meta(sdir) or {}
    if meta.get("world") != name:
        return [f"not rendered as part of world {name}"]
    out = []
    latest = latest_world(project, name)
    if latest is not None and latest.name != meta.get("world_version"):
        if latest_world_render(project, name) == latest:
            out.append(f"world version {latest.name} is newer than {meta.get('world_version')}, the one rendered")
        else:
            out.append(f"world version {latest.name} is scaffolded and not rendered")
    wdir = world_root(project, name) / str(meta.get("world_version"))
    try:
        p, timing = plan(project, data, name)
    except SceneError as e:
        return out + [str(e)]
    if not (wdir / WORLD_JSON).is_file():
        return out + [f"world version {meta.get('world_version')} is missing"]
    if json.loads((wdir / WORLD_JSON).read_text(encoding="utf-8")) != p.to_dict():
        out.append("the world's scenes, voice versions or lengths changed; run `scaffold` and `render` again")
    elif (wdir / "brief.md").read_text(encoding="utf-8") != brief_markdown(data, p, timing):
        out.append("the world's brief.md differs from the storyboard (a scene's Brief or On screen text)")
    return out
