"""Video-model scenes (`Engine: video`): `scaffold` writes `prompt.txt` (the motion prompt, first the
scene's `Brief:`) and `background.png` (the still to animate); `render` sends both to
`ai_models.video.animate`, fits the clip to the narration (`fill`) and finishes it like any scene
(references/video-model.md)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import clip, media, settings, state, storyboard, versions
from .engine import Engine
from .scenes import BACKGROUND, SceneError, _latest_timing, _scene_voice, brief_markdown, finish

PROMPT = "prompt.txt"
MODEL_MP4 = "model.mp4"


def video_brief(scene: dict, timing: dict, voice_version: str) -> str:
    """`brief.md` of an HTML scene plus a section on the video-model files."""
    v = settings.get()["video"]
    return brief_markdown(scene, timing, voice_version) + "\n".join([
        "## Video model",
        "",
        f"- Engine: a video model (task `video` of the ai_models config) animates `{BACKGROUND}` from "
        f"`{PROMPT}`; `references/video-model.md` has the rules.",
        f"- `{PROMPT}` starts as the Brief; write it as the motion of the image, then run `render`.",
        f"- Render: {v['width']}x{v['height']}, {v['fps']} fps, {timing['duration']:.2f} s; a shorter clip "
        "holds its last frame to the end of the narration, a longer one is cut there.",
        "",
    ])


def fill_filter(clip_seconds: float, scene_seconds: float) -> str:
    """The `-vf` that makes a model clip a scene video: scale to cover the
    `video:` frame, crop the centre, then `clip.video_filter` (fps, SAR 1:1,
    pixel format, the last frame held for the time the scene runs past the clip)."""
    v = settings.get()["video"]
    w, h = v["width"], v["height"]
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            + clip.video_filter(clip_seconds, scene_seconds))


def fill_command(src: Path, dest: Path, clip_seconds: float, scene_seconds: float) -> list:
    """The FFmpeg command that writes `dest`, exactly `scene_seconds` long, from
    the model clip `src` (`fill_filter`, then cut at `scene_seconds`)."""
    e = settings.encode()
    return [media.which("ffmpeg"), "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-an",
            "-vf", fill_filter(clip_seconds, scene_seconds), "-t", media.num(scene_seconds),
            "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"], dest]


def fill(src: Path, dest: Path, scene_seconds: float) -> float:
    """Write `dest` from the model clip `src` (`fill_command`). Returns the clip's length."""
    clip_seconds = media.video_duration(src)
    media.run(fill_command(src, dest, clip_seconds, scene_seconds))
    return clip_seconds


def scaffold(project: Path, scene: dict) -> Path:
    """Create the next version of a video scene and return its directory."""
    sid = scene["id"]
    if not storyboard.is_video(scene):
        raise SceneError(f"scene {sid} is not a video scene")
    vdir, timing = _latest_timing(project, sid)
    image = storyboard.image_path(project, scene["image"])
    if not image.is_file():
        raise SceneError(f"scene {sid}: image {image} not found")

    previous = state.latest_scene(project, sid)
    out = versions.next_version(state.scene_root(project, sid))
    if previous is not None and (previous / PROMPT).is_file():
        shutil.copyfile(previous / PROMPT, out / PROMPT)
    else:
        (out / PROMPT).write_text(str(scene["brief"]).strip() + "\n", encoding="utf-8")
    (out / "timing.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(image, out / BACKGROUND)
    (out / "brief.md").write_text(video_brief(scene, timing, vdir.name), encoding="utf-8")
    (out / "voice_version").write_text(vdir.name + "\n")
    return out


def render(project: Path, scene: dict, seed: int | None = None) -> Path:
    """Model call, fill to the narration's length, mux narration, contact
    sheet, meta. Returns scene.mp4."""
    sid = scene["id"]
    sdir = state.latest_scene(project, sid)
    if sdir is None or not (sdir / PROMPT).is_file() or not (sdir / BACKGROUND).is_file():
        raise SceneError(f"scene {sid}: no video scene to render; run `scaffold` first")
    prompt = " ".join((sdir / PROMPT).read_text(encoding="utf-8").split())
    if not prompt:
        raise SceneError(f"{sdir / PROMPT} is empty; write the motion prompt")
    timing = json.loads((sdir / "timing.json").read_text(encoding="utf-8"))
    vdir = _scene_voice(project, sdir)
    seconds = float(timing["duration"])
    v = settings.get()["video"]

    from ai_models import config as ai_config
    from ai_models import video
    from ai_models.errors import AIModelsError

    try:
        model = ai_config.resolve(None, "video")
        mp4 = video.animate((sdir / BACKGROUND).read_bytes(), prompt, seconds=seconds, model=model,
                            width=v["width"], height=v["height"], seed=seed)
    except AIModelsError as e:
        raise SceneError(f"scene {sid}: video model: {e}") from None
    (sdir / MODEL_MP4).write_bytes(mp4)

    silent = sdir / "silent.mp4"
    clip_seconds = fill(sdir / MODEL_MP4, silent, seconds)
    return finish(sdir, silent, ["-i", vdir / "narration.wav"], {
        "scene": sid, "voice_version": vdir.name, "engine": Engine.VIDEO, "model": model, "prompt": prompt,
        "seed": seed, "clip_duration": round(clip_seconds, 3),
    })
