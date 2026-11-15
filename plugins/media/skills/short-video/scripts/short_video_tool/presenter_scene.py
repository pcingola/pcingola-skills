"""Presenter scenes (`Engine: presenter`): a presenter model (task `presenter` of the ai_models config) makes the
person in the scene's picture speak the scene's narration recording. `scaffold` copies the picture as
`background.png`; `render` sends it and the voice version's `narration.wav` to `ai_models.video.present`, with the
scene's `Brief:` as the prompt when it has one (else the model's own prompt), so the model's frame size is the
bucket nearest the picture's aspect ratio; fits the clip into the frame uncropped and to the narration
(`video_scene.fill`, `Fit.CONTAIN`) and finishes it like any scene with the narration as its sound
(references/video-model.md, "Presenter scenes")."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import settings, state, storyboard, versions
from .engine import Engine
from .fit import Fit
from .scenes import BACKGROUND, SceneError, _latest_timing, _scene_voice, brief_markdown, finish
from .video_scene import MODEL_MP4, fill

NARRATION = "narration.wav"
FIT = Fit.CONTAIN  # the bucket follows the picture, so the clip is fitted into the frame uncropped


def presenter_brief(scene: dict, timing: dict, voice_version: str) -> str:
    """`brief.md` of an HTML scene plus a section on the presenter model."""
    v = settings.get()["video"]
    prompt = f"the Brief: {' '.join(str(scene['brief']).split())}" if scene.get("brief") else "the model's own"
    return brief_markdown(scene, timing, voice_version) + "\n".join([
        "## Presenter model",
        "",
        f"- Engine: a presenter model (task `presenter` of the ai_models config) makes the person in "
        f"`{BACKGROUND}` speak `{NARRATION}` of voice {voice_version}; `references/video-model.md` has the rules.",
        f"- Prompt: {prompt}.",
        f"- Render: the model's frame size nearest the picture's aspect ratio, scaled to fit inside "
        f"{v['width']}x{v['height']} uncropped over a blurred copy of the clip; "
        f"{timing['duration']:.2f} s, the length of the recording.",
        "",
    ])


def speech_digest(path: Path) -> str:
    """The SHA-256 of a narration recording, kept in meta.json so that `status` sees a changed recording."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scaffold(project: Path, scene: dict) -> Path:
    """Create the next version of a presenter scene and return its directory."""
    sid = scene["id"]
    if Engine.of(scene) != Engine.PRESENTER:
        raise SceneError(f"scene {sid} is not a presenter scene")
    vdir, timing = _latest_timing(project, sid)
    image = storyboard.image_path(project, scene["image"])
    if not image.is_file():
        raise SceneError(f"scene {sid}: image {image} not found")
    out = versions.next_version(state.scene_root(project, sid))
    (out / "timing.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(image, out / BACKGROUND)
    (out / "brief.md").write_text(presenter_brief(scene, timing, vdir.name), encoding="utf-8")
    (out / "voice_version").write_text(vdir.name + "\n")
    return out


def render(project: Path, scene: dict, seed: int | None = None) -> Path:
    """Model call, fill to the narration's length, mux the narration, contact sheet, meta. Returns scene.mp4."""
    sid = scene["id"]
    sdir = state.latest_scene(project, sid)
    if sdir is None or not (sdir / BACKGROUND).is_file() or not (sdir / "timing.json").is_file():
        raise SceneError(f"scene {sid}: no presenter scene to render; run `scaffold` first")
    timing = json.loads((sdir / "timing.json").read_text(encoding="utf-8"))
    vdir = _scene_voice(project, sdir)
    seconds = float(timing["duration"])
    prompt = " ".join(str(scene.get("brief") or "").split()) or None

    from ai_models import config as ai_config
    from ai_models import video
    from ai_models.errors import AIModelsError

    speech = vdir / NARRATION
    try:
        model = ai_config.resolve(None, "presenter")
        mp4 = video.present((sdir / BACKGROUND).read_bytes(), speech.read_bytes(), model=model, aspect=None,
                            prompt=prompt, seed=seed)
    except AIModelsError as e:
        raise SceneError(f"scene {sid}: presenter model: {e}") from None
    (sdir / MODEL_MP4).write_bytes(mp4)

    silent = sdir / "silent.mp4"
    clip_seconds = fill(sdir / MODEL_MP4, silent, seconds, FIT)
    return finish(sdir, silent, ["-i", speech], {
        "scene": sid, "voice_version": vdir.name, "engine": Engine.PRESENTER, "model": model, "prompt": prompt,
        "seed": seed, "clip_duration": round(clip_seconds, 3), "speech_sha256": speech_digest(speech),
    })
