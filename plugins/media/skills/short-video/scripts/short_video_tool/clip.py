"""Clip scenes: import a video made elsewhere as a scene version.

A scene with `Engine: clip` has no page to render. `clip --scene ID FILE`
checks that FILE has a video stream at the `video:` size and frame rate,
copies it into the next scene version as `clip<suffix>`, and writes
`silent.mp4` re-encoded as the other engines write it (the `encode:` codec,
pixel format and CRF, SAR 1:1, the `video:` fps), so `assemble` joins it with
HTML and manim scenes. Then `scenes.finish` writes `scene.mp4`, the contact
sheet and `meta.json` (`"engine": "clip"`).

Without narration the scene lasts the clip and its audio is silence. With
narration (the latest voice version) the clip's last frame is held until the
narration ends when the clip is shorter; a longer clip sets the scene length
and the narration is padded with silence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from fractions import Fraction
from pathlib import Path

from . import config, media, settings, state, storyboard, versions
from .scenes import SceneError, brief_head, brief_sentences, finish, silent_audio

ENGINE = storyboard.CLIP
CLIP_STEM = "clip"


def refuse(scene_id: str, command: str) -> str:
    """The message of `render` and `scaffold` on a clip scene."""
    return (f"scene {scene_id} is a clip scene (`Engine: clip`); `{command}` does not apply. "
            f"Import its video with `clip --scene {scene_id} FILE`")


def stream_format(info: dict) -> tuple[int, int, Fraction]:
    """(width, height, frame rate) of the first video stream of an ffprobe result."""
    s = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if s is None:
        raise SceneError("no video stream")
    rate = s.get("r_frame_rate") or s.get("avg_frame_rate") or "0/1"
    return int(s["width"]), int(s["height"]), Fraction(rate)


def check_format(path: Path, info: dict) -> None:
    """Raise SceneError unless the video is at the `video:` size and fps."""
    v = settings.get()["video"]
    try:
        w, h, fps = stream_format(info)
    except SceneError:
        raise SceneError(f"{path} has no video stream") from None
    if (w, h) != (v["width"], v["height"]) or not same_rate(fps, v["fps"]):
        raise SceneError(
            f"{path} is {w}x{h} at {float(fps):g} fps; the film needs {v['width']}x{v['height']} at "
            f"{v['fps']} fps (`video:` in settings.yaml). Make the clip again at that size and frame rate")


def same_rate(rate: Fraction, fps: float) -> bool:
    """True when a stream's frame rate is the `video.fps` value: equal after
    rounding both to a denominator of at most 1001, or within 0.001 fps, so
    `fps: 29.97` matches NTSC's 30000/1001."""
    want = Fraction(str(fps)).limit_denominator(1001)
    return rate.limit_denominator(1001) == want or abs(float(rate) - float(want)) < 1e-3


def has_audio(info: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def video_filter(clip_seconds: float, scene_seconds: float) -> str:
    """The `-vf` of `silent.mp4`: the `video:` fps, SAR 1:1, the pixel format,
    and the last frame held for the time the scene runs past the clip."""
    e, v = settings.encode(), settings.get()["video"]
    vf = [f"fps={v['fps']}", "setsar=1", f"format={e['pixel_format']}"]
    hold = scene_seconds - clip_seconds
    if hold > 0:
        vf.append(f"tpad=stop_mode=clone:stop_duration={media.num(hold)}")
    return ",".join(vf)


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def brief_markdown(scene: dict, source: Path, clip_seconds: float, voice: Path | None,
                   timing: dict | None) -> str:
    """`brief.md` of a clip scene: what the clip shows, its source and length,
    and, when narrated, the sentence and word times of the voice version."""
    lines = brief_head(scene, [
        f"- Engine: clip, imported from `{source}`, {clip_seconds:.2f} s",
        f"- Image: `{scene['image']}`" if scene.get("image") else "- Image: none",
        f"- Narration: voice {voice.name}, {timing['duration']:.2f} s" if voice and timing
        else "- Narration: none (silent)",
    ])
    return "\n".join(lines + (brief_sentences(scene, timing) if timing else []))


def import_clip(project: Path, scene: dict, src: Path) -> Path:
    """Import `src` as the next version of the clip scene `scene`. Returns scene.mp4."""
    sid = scene["id"]
    if not storyboard.is_clip(scene):
        raise SceneError(f"scene {sid} is not a clip scene; give it `Engine: clip` in the storyboard")
    if not src.is_file():
        raise SceneError(f"{src} not found")
    vdir = None
    if storyboard.narrated(scene):
        vdir = state.latest_voice(project, sid)
        if vdir is None or not (vdir / "narration.wav").is_file():
            raise SceneError(f"scene {sid}: no voice yet; run `script`, voice it, run `voice`, then `clip`")
    info = media.probe(src)
    check_format(src, info)
    if has_audio(info):
        config.warn(f"{src} has an audio stream; the clip's audio is not used")
    clip_seconds = media.video_duration(src)
    narration_seconds = media.duration(vdir / "narration.wav") if vdir else None
    timing = json.loads((vdir / "timing.json").read_text(encoding="utf-8")) if vdir else None
    scene_seconds = max(clip_seconds, narration_seconds or 0.0)

    out = versions.next_version(state.scene_root(project, sid))
    try:
        dest = out / f"{CLIP_STEM}{src.suffix.lower() or '.mp4'}"
        shutil.copyfile(src, dest)
        e = settings.encode()
        silent = out / "silent.mp4"
        media.run([
            media.which("ffmpeg"), "-y", "-v", "error", "-i", dest, "-map", "0:v:0", "-an",
            "-vf", video_filter(clip_seconds, scene_seconds),
            "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"], silent,
        ])
        (out / "brief.md").write_text(brief_markdown(scene, src, clip_seconds, vdir, timing),
                                      encoding="utf-8")
        v = settings.get()["video"]
        audio = ["-i", vdir / "narration.wav"] if vdir else silent_audio()
        return finish(out, silent, audio, {
            "scene": sid,
            "voice_version": vdir.name if vdir else None,
            "engine": ENGINE,
            "source": str(src.resolve()),
            "sha256": sha256(dest),
            "clip": dest.name,
            "clip_duration": round(clip_seconds, 3),
            "width": v["width"],
            "height": v["height"],
        })
    except BaseException:
        # Leave no half-written version behind; its number is still never reused.
        shutil.rmtree(out)
        raise

