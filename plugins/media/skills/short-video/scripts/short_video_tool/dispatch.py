"""`scaffold` and `render` of a scene through its engine: HyperFrames (`scenes`, or `world` for a scene of a
world), Manim (`manim_scene`), the video model (`video_scene`) or the presenter model (`presenter_scene`). A clip
scene (`clip`) has neither."""

from __future__ import annotations

from pathlib import Path

from . import clip, config, manim_scene, presenter_scene, scenes, state, storyboard, video_scene, world
from .scenes import SceneError


def _is_model_or_manim(scene: dict) -> bool:
    return manim_scene.is_manim(scene) or storyboard.is_video(scene) or storyboard.is_presenter(scene)


def scaffold(project: Path, data: dict, scene_id: str, node_dir: Path, refresh: bool = False,
             estimate: bool = False) -> list[Path]:
    """Create the next version of scene `scene_id` of the storyboard `data` (a scene of a world: the world's next
    version) and return the files the author edits or reads in it: the page, scene.py or prompt.txt, then
    brief.md. An HTML scene or world first installs HyperFrames in `node_dir` when missing (`scenes.ensure_node`).
    `refresh` rewrites the latest HTML version in place; `estimate` times an HTML page from the narration's words.
    Raises StoryboardError for an unknown scene and SceneError for a clip scene, an option that does not apply
    to the scene's engine, or a failed scaffold."""
    scene = storyboard.scene_by_id(data, scene_id)
    if storyboard.is_clip(scene):
        raise SceneError(clip.refuse(scene_id, "scaffold"))
    if refresh and _is_model_or_manim(scene):
        raise SceneError("--refresh applies to HTML scenes and worlds only")
    if manim_scene.is_manim(scene):
        out = manim_scene.scaffold(project, scene)
        return [out / manim_scene.SCENE_PY, out / "brief.md"]
    if storyboard.is_video(scene):
        out = video_scene.scaffold(project, scene)
        return [out / video_scene.PROMPT, out / "brief.md"]
    if storyboard.is_presenter(scene):
        return [presenter_scene.scaffold(project, scene) / "brief.md"]
    if estimate and storyboard.world_name(scene):
        raise SceneError("--estimate applies to an HTML scene without a world only")
    scenes.ensure_node(node_dir, config.NODE_SRC)
    if name := storyboard.world_name(scene):
        out = world.scaffold(project, data, name, node_dir, refresh)
    else:
        out = scenes.scaffold(project, scene, node_dir, refresh, estimate)
    return [out / "index.html", out / "brief.md"]


def render(project: Path, data: dict, scene_id: str, node_dir: Path, manim_env: Path | None,
           seed: int | None = None, model: str | None = None) -> list[Path]:
    """Render the latest version of scene `scene_id` of the storyboard `data` and return each scene.mp4 written
    (a scene of a world: one per scene of the world), each with `contact.png` beside it. A Manim scene runs in the
    Manim environment `manim_env`; a video or presenter scene calls its model with `seed` and `model`; an HTML
    scene or world renders with HyperFrames in `node_dir`, installed first when missing. Raises StoryboardError
    for an unknown scene, SceneError for a clip scene, `seed` or `model` on another engine, a latest HTML version
    without a page or a failed render, and media.ToolError for a failed tool."""
    scene = storyboard.scene_by_id(data, scene_id)
    if storyboard.is_clip(scene):
        raise SceneError(clip.refuse(scene_id, "render"))
    if manim_scene.is_manim(scene):
        return [manim_scene.render(project, scene, manim_env)]
    if storyboard.is_video(scene):
        return [video_scene.render(project, scene, seed, model)]
    if storyboard.is_presenter(scene):
        return [presenter_scene.render(project, scene, seed, model)]
    if seed is not None or model is not None:
        raise SceneError("--seed and --model apply only to a video or presenter scene (`Engine: video`, "
                         "`Engine: presenter`)")
    if name := storyboard.world_name(scene):
        scenes.ensure_node(node_dir, config.NODE_SRC)
        return world.render(project, data, name, node_dir)
    # A scene switched from manim to html has a latest version with no page.
    latest = state.latest_scene(project, scene_id)
    if latest is not None and not (latest / "index.html").is_file():
        raise SceneError(f"scene {scene_id}: latest version {latest.name} has no index.html; run `scaffold` first")
    scenes.ensure_node(node_dir, config.NODE_SRC)
    return [scenes.render(project, scene, node_dir)]
