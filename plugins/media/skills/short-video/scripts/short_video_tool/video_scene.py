"""Video-model scenes (`Engine: video`): `scaffold` writes `prompt.txt` (the motion prompt, first the
scene's `Brief:`) and `background.png` (the still to animate); `render` sends both to
`ai_models.video.animate`, fits the clip to the narration (`fill`), mixes the clip's sound track under
the narration as ambience, leveled to the narration, when it has one (`mix_ambience`) and finishes it like any scene
(references/video-model.md)."""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from . import clip, media, settings, state, storyboard, versions
from .engine import Engine
from .fit import Fit
from .scenes import BACKGROUND, SceneError, _latest_timing, _scene_voice, brief_markdown, finish

PROMPT = "prompt.txt"
MODEL_MP4 = "model.mp4"
AUDIO_WAV = "audio.wav"


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


BLUR = 40  # `boxblur` radius of the background of a `Fit.CONTAIN` clip, in pixels of the `video:` frame


def fill_filter(clip_seconds: float, scene_seconds: float, fit: Fit = Fit.COVER) -> str:
    """The `-vf` that makes a model clip a scene video: fit the clip to the `video:` frame (`fit`: cover and crop
    the centre, or contain over a blurred copy of the clip that covers the frame), then `clip.video_filter`
    (fps, SAR 1:1, pixel format, the last frame held for the time the scene runs past the clip)."""
    v = settings.get()["video"]
    w, h = v["width"], v["height"]
    cover = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if fit == Fit.CONTAIN:
        cover = (f"split[bg][fg];[bg]{cover},boxblur={BLUR}[bg];"
                 f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"{cover}," + clip.video_filter(clip_seconds, scene_seconds)


def fill_command(src: Path, dest: Path, clip_seconds: float, scene_seconds: float, fit: Fit = Fit.COVER) -> list:
    """The FFmpeg command that writes `dest`, exactly `scene_seconds` long, from
    the model clip `src` (`fill_filter`, then cut at `scene_seconds`)."""
    e = settings.encode()
    return [media.which("ffmpeg"), "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-an",
            "-vf", fill_filter(clip_seconds, scene_seconds, fit), "-t", media.num(scene_seconds),
            "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"], dest]


def fill(src: Path, dest: Path, scene_seconds: float, fit: Fit = Fit.COVER) -> float:
    """Write `dest` from the model clip `src` (`fill_command`). Returns the clip's length."""
    clip_seconds = media.video_duration(src)
    media.run(fill_command(src, dest, clip_seconds, scene_seconds, fit))
    return clip_seconds


def ambience_filter(clip_seconds: float, scene_seconds: float, gain_db: float) -> str:
    """The `-filter_complex` that mixes input 0 (the narration) with the audio of input 1 (the model clip) at
    `gain_db`, both in the film's sample rate and channel layout. The ambience fades in and out over
    `mix.ambience_fade` seconds, ends with the clip or the scene, whichever is first, and is padded with silence
    to the scene's length. Output `[a]`."""
    m, layout = settings.get()["mix"], settings.encode()["channel_layout"]
    fmt = f"aresample={m['sample_rate']},aformat=sample_fmts=fltp:channel_layouts={layout}"
    end = min(clip_seconds, scene_seconds)
    fade = min(m["ambience_fade"], end / 2)
    num = media.num
    return ";".join([
        f"[0:a:0]{fmt}[voice]",
        f"[1:a:0]{fmt},atrim=0:{num(end)},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={num(fade)},"
        f"afade=t=out:st={num(end - fade)}:d={num(fade)},volume={num(gain_db)}dB,"
        f"apad=whole_dur={num(scene_seconds)}[amb]",
        "[voice][amb]amix=inputs=2:normalize=0:duration=longest[a]",
    ])


def ambience_level(scene: dict, model_clip: Path) -> float | None:
    """The ambience level a render of `scene` gives `model_clip`'s sound track, in LU relative to the narration:
    `mix.ambience_relative_db` when the clip has an audio stream and the scene's `ambience` is not False, else None
    (the narration alone)."""
    if scene.get("ambience", True) and clip.has_audio(media.probe(model_clip)):
        return settings.get()["mix"]["ambience_relative_db"]
    return None


def loudness(path: Path, seconds: float) -> float:
    """Integrated loudness (LUFS, EBU R128, `ebur128`) of the first audio stream of `path` over its first
    `seconds`; -inf for silence."""
    err = media.run([media.which("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0",
                     "-af", f"atrim=0:{media.num(seconds)},ebur128", "-f", "null", "-"]).stderr
    found = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", err)
    if not found:
        raise SceneError(f"{path}: ebur128 printed no integrated loudness")
    return float(found[-1])


def ambience_gain(narration_lufs: float, ambience_lufs: float, relative_db: float, max_gain_db: float) -> float:
    """The gain (dB) that puts the ambience `relative_db` LU from the narration's loudness, at most `max_gain_db`,
    so a near-silent track is not raised into noise."""
    return min(narration_lufs + relative_db - ambience_lufs, max_gain_db)


def mix_ambience(narration: Path, model_clip: Path, dest: Path, clip_seconds: float, scene_seconds: float) -> dict:
    """Write `dest` (32-bit float WAV, so the sum does not clip before the film's loudness pass): the narration
    with the model clip's sound track under it, leveled to `mix.ambience_relative_db` from the narration's
    integrated loudness (the film's `mix.loudness_i` when the narration is silent; `ambience_gain`, capped at `mix.ambience_max_gain_db`; `ambience_filter`). Returns the
    measured loudness and the gain for meta.json."""
    m = settings.get()["mix"]
    voice = loudness(narration, scene_seconds)
    reference = voice if math.isfinite(voice) else m["loudness_i"]  # a silent narration: the film's target
    track = loudness(model_clip, min(clip_seconds, scene_seconds))
    gain = ambience_gain(reference, track, m["ambience_relative_db"], m["ambience_max_gain_db"])
    media.run([media.which("ffmpeg"), "-y", "-v", "error", "-i", narration, "-i", model_clip,
               "-filter_complex", ambience_filter(clip_seconds, scene_seconds, gain), "-map", "[a]",
               "-c:a", "pcm_f32le", dest])
    return {"narration_lufs": voice, "ambience_lufs": track, "ambience_gain_db": round(gain, 2)}


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


def render(project: Path, scene: dict, seed: int | None = None, model: str | None = None) -> Path:
    """Model call (`model`, else task `video` of the ai_models config), fill to the narration's length, mux the narration (with the
    clip's sound track under it unless the scene has `ambience` False), contact
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
        model = ai_config.resolve(model, "video")
        # the model renders at its own size in the project's aspect ratio; `fill` scales the clip to `video:`
        mp4 = video.animate((sdir / BACKGROUND).read_bytes(), prompt, seconds=seconds, model=model,
                            aspect=v["width"] / v["height"], seed=seed)
    except AIModelsError as e:
        raise SceneError(f"scene {sid}: video model: {e}") from None
    (sdir / MODEL_MP4).write_bytes(mp4)

    silent = sdir / "silent.mp4"
    clip_seconds = fill(sdir / MODEL_MP4, silent, seconds)
    audio = vdir / "narration.wav"
    level = ambience_level(scene, sdir / MODEL_MP4)
    measured = {}
    if level is not None:
        measured = mix_ambience(audio, sdir / MODEL_MP4, sdir / AUDIO_WAV, clip_seconds, seconds)
        audio = sdir / AUDIO_WAV
    return finish(sdir, silent, ["-i", audio], {
        "scene": sid, "voice_version": vdir.name, "engine": Engine.VIDEO, "model": model, "prompt": prompt,
        "seed": seed, "clip_duration": round(clip_seconds, 3), "ambience_relative_db": level, **measured,
    })
