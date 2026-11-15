"""Argparse dispatcher for `short-video <command>`.

Commands:
    init       Create a film project, copy the PNGs and source text if given,
               write settings.yaml and a storyboard.md (or, with --json,
               storyboard.json) template.
    validate   Check the storyboard and estimate the film length.
    storyboard Print the storyboard as storyboard.json stores it.
    status     Print, per scene, whether it needs a new voice recording or a
               new render (JSON).
    script     Write each scene's narration script (one sentence per line)
               to sources/narration/<scene>/ for the voiceover skill (one
               p<k>/ part per run of voices; prints each part's voice when it
               is not the film's `voice:`).
    voice      Import the narration voiced there as the next voice version,
               after checking it against the storyboard.
    scaffold   Create the next version of a scene's composition.
    render     Check, lint and render a scene (a video scene: animate its image
               with the video model); mux its narration; contact sheet.
    clip       Import a video made elsewhere as the next version of a clip scene.
    frames     Extract full-size frames of a rendered scene at given times.
    music      Import music.file (made with the music skill) as the next
               music version.
    length     Print the narration length and the music length to request.
    critic     Print the film critic's model: `critic.model` of settings.yaml,
               else task `film_critic` of the ai_models config; `off` when
               `critic.model` is null.
    assemble   Join all scenes, mix the music under the voice, draw the creator
               caption: film/v<N>/film.mp4.
    credit     Add the creator caption and metadata to an existing MP4.
    audiocheck Find high-frequency bursts and clicks in audio files, or in each
               track a film is mixed from.
    setup      Install the pinned HyperFrames/GSAP and the render browser.
    play       Open a media file in the player set in assets/settings.yaml.

Every command except `init`, `credit`, `audiocheck FILE`, `setup` and `play`
works on the project given by `--project` (a path; default: the current
directory) and reads its `settings.yaml` over the skill defaults.

`scaffold` and `render` of a scene with `Engine: manim` work on its Manim
`scene.py` (`manim_scene`) instead of an HTML composition and need no
HyperFrames. Those of a scene with `Engine: video` work on its motion prompt
`prompt.txt` (`video_scene`): `render` sends the scene's image and the prompt
to the video model (`render --seed N` fixes the model's seed, `render --model
ID` replaces the model). Those of a
scene with `Engine: presenter` (`presenter_scene`) copy its picture, and
`render` sends it and the scene's narration recording to the presenter model
(`--seed` and `--model` too). `routes` prints the model routes of the video
and presenter tasks (`ai_models.routes`). A scene with
`Engine: clip` has no page: `clip` imports its video (`clip`), and
`scaffold` and `render` refuse it.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from ai_models import routes

from . import audiocheck, brand, clip, config, credit, media, mix, music, narration, scenes, settings, speakers, state
from . import manim_scene, presenter_scene, status, storyboard, video_scene

# The tasks of video and presenter scenes; `routes` prints their rows.
ROUTE_TASKS = ("video", "presenter")
LAYOUT = ("images", "sources", "voice", "scenes", "music", "film")


def _project(args: argparse.Namespace) -> Path:
    p = config.resolve_project(args.project)
    if not p.is_dir():
        config.error(f"project {p} does not exist; run `init` first")
    settings.use_project(p)
    return p


def _load(project: Path) -> dict:
    try:
        return storyboard.load(project)
    except storyboard.StoryboardError as e:
        config.error(str(e))


def _valid(project: Path) -> dict:
    data = _load(project)
    v = storyboard.validate(data, project)
    if not v.ok:
        config.error(f"{storyboard.source_file(project).name} is invalid:\n  " + "\n  ".join(v.errors))
    return data


def _scene(data: dict, scene_id: str) -> dict:
    try:
        return storyboard.scene_by_id(data, scene_id)
    except storyboard.StoryboardError as e:
        config.error(str(e))


def _ensure_node() -> None:
    if not scenes.node_ready(config.NODE_DIR, config.NODE_SRC):
        print("HyperFrames not installed or package-lock.json changed; running setup", file=sys.stderr)
        try:
            scenes.setup(config.NODE_DIR, config.NODE_SRC)
        except (scenes.SceneError, media.ToolError) as e:
            config.error(str(e))


# ---------------------------------------------------------------------------


def authors(names: list[str] | None) -> str | None:
    """Repeated `credit --author` values as one string: names joined with ", "."""
    names = [" ".join(n.split()) for n in names or []]
    return ", ".join(n for n in names if n) or None


def _audio_warnings(path: Path, name: str | None = None) -> None:
    """Print each audio defect in `path` as a warning; never fails the command."""
    try:
        found = audiocheck.check(path)
    except Exception as e:
        config.warn(f"audio check of {path} failed: {e}")
        return
    for line in found:
        config.warn(f"audio: {name or path} {line}")


def _cmd_init(args: argparse.Namespace) -> int:
    project = config.resolve_project(args.project)
    if project.exists() and not project.is_dir():
        config.error(f"{project} exists and is not a directory")
    if project.exists() and any(project.iterdir()):
        config.error(f"{project} already exists and is not empty")
    pngs = []
    if args.images:
        images = Path(args.images).expanduser()
        pngs = sorted(p for p in images.iterdir() if p.is_file() and p.suffix.lower() == ".png") if images.is_dir() else []
        if not pngs:
            config.error(f"no PNG files in {images}")
    for d in LAYOUT:
        (project / d).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(settings.SETTINGS_FILE, project / settings.PROJECT_FILE)
    settings.use_project(project)
    for p in pngs:
        shutil.copyfile(p, project / "images" / p.name)
    if args.source:
        src = Path(args.source).expanduser()
        if not src.is_file():
            config.error(f"source file {src} not found")
        shutil.copyfile(src, project / "sources" / src.name)
    lessons = project / "lessons.md"
    if not lessons.exists():
        lessons.write_text(settings.asset("lessons.md"), encoding="utf-8")
    title = project.name.replace("-", " ").replace("_", " ").capitalize()
    name, make = ((storyboard.JSON_FILE, storyboard.json_template) if args.json
                  else (storyboard.MD_FILE, storyboard.template))
    (project / name).write_text(make(title, [p.name for p in pngs]), encoding="utf-8")
    _load(project)
    print(project)
    print(f"  {settings.PROJECT_FILE}")
    print(f"  {name}")
    for p in pngs:
        print(f"  images/{p.name}")
    return 0


def _brand_dir(args: argparse.Namespace) -> Path | None:
    return Path(args.brand).expanduser() if args.brand else None


def _cmd_validate(args: argparse.Namespace) -> int:
    project = _project(args)
    try:
        data = storyboard.load(project)
    except storyboard.StoryboardError as e:
        for line in str(e).splitlines():
            print(f"error: {line}")
        return 1
    v = storyboard.validate(data, project, _brand_dir(args))
    for e in v.errors:
        print(f"error: {e}")
    for w in v.warnings:
        print(f"warning: {w}")
    print(f"scenes: {len(storyboard.scenes(data))}, estimated length: {v.estimated_seconds:.0f} s")
    return 0 if v.ok else 1


def _cmd_storyboard(args: argparse.Namespace) -> int:
    project = _project(args)
    try:
        data = storyboard.read(project)
    except storyboard.StoryboardError as e:
        config.error(str(e))
    print(storyboard.to_json(data), end="")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    project = _project(args)
    print(json.dumps(status.report(project, _load(project)), indent=2, ensure_ascii=False))
    return 0


def _targets(data: dict, ids: list[str] | None, pending) -> list[dict]:
    """The narrated scenes named, or every narrated scene for which
    `pending(scene)` holds; a clip scene without narration is never one."""
    if ids:
        named = [_scene(data, sid) for sid in ids]
        silent = [s["id"] for s in named if not storyboard.narrated(s)]
        if silent:
            config.error(f"scene(s) {', '.join(silent)} have no narration table (a silent clip scene)")
        return named
    return [s for s in storyboard.scenes(data) if storyboard.narrated(s) and pending(s)]


def _voice_line(speaker: str | None, voice: dict) -> str:
    """The voice to voice a script with, as `script` prints it."""
    return " ".join(([f"speaker={speaker}"] if speaker else []) + ([f"model={voice['model']}"] if voice["model"] else [])
                    + ([f"name={voice['name']}"] if voice["name"] else [])
                    + [f"speed={voice['speed']}"] + ([f"style={voice['style']}"] if voice["style"] else []))


def _cmd_script(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    film = storyboard.resolve_voice(data)
    targets = _targets(data, args.scene, lambda s: state.latest_voice(project, s["id"]) is None)
    for s in targets:
        for path, speaker, voice in narration.write_script(project, data, s):
            print(path)
            if speaker is not None or voice != film:
                print("  " + _voice_line(speaker, voice))
    if not targets:
        print("every scene has narration; name scenes with --scene to write their scripts again")
    return 0


def _cmd_voice(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)

    def voiced(s: dict) -> bool:
        if narration.is_multipart(data, s):
            n = len(speakers.runs(data, s))
            return all((speakers.part_dir(project, s["id"], k) / "timing.json").is_file() for k in range(1, n + 1))
        return (narration.script_dir(project, s["id"]) / "timing.json").is_file()

    def pending(s: dict) -> bool:
        return state.latest_voice(project, s["id"]) is None and voiced(s)

    targets = _targets(data, args.scene, pending)
    for s in targets:
        src = Path(args.src).expanduser() if args.src else narration.script_dir(project, s["id"])
        try:
            out = narration.import_voice(project, data, s, src)
        except narration.NarrationError as e:
            config.error(str(e))
        print(out / "narration.wav")
        _audio_warnings(out / "narration.wav", str((out / "narration.wav").relative_to(project)))
    if not targets:
        print("nothing to import: voice `sources/narration/<scene>/script.txt` (or every "
              "`sources/narration/<scene>/p<k>/script.txt`) with the voiceover skill first, "
              "or name scenes with --scene")
    return 0


def _scaffold_manim(project: Path, scene: dict) -> int:
    try:
        out = manim_scene.scaffold(project, scene)
    except scenes.SceneError as e:
        config.error(str(e))
    print(out / manim_scene.SCENE_PY)
    print(out / "brief.md")
    return 0


def _render_manim(project: Path, scene: dict) -> int:
    try:
        out = manim_scene.render(project, scene)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    print(out.parent / "contact.png")
    return 0


def _scaffold_video(project: Path, scene: dict) -> int:
    try:
        out = video_scene.scaffold(project, scene)
    except scenes.SceneError as e:
        config.error(str(e))
    print(out / video_scene.PROMPT)
    print(out / "brief.md")
    return 0


def _render_video(project: Path, scene: dict, seed: int | None, model: str | None) -> int:
    try:
        out = video_scene.render(project, scene, seed, model)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    print(out.parent / "contact.png")
    return 0


def _scaffold_presenter(project: Path, scene: dict) -> int:
    try:
        out = presenter_scene.scaffold(project, scene)
    except scenes.SceneError as e:
        config.error(str(e))
    print(out / "brief.md")
    return 0


def _render_presenter(project: Path, scene: dict, seed: int | None, model: str | None) -> int:
    try:
        out = presenter_scene.render(project, scene, seed, model)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    print(out.parent / "contact.png")
    return 0


def _cmd_scaffold(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    if storyboard.is_clip(_scene(data, args.scene)):
        config.error(clip.refuse(args.scene, "scaffold"))
    if manim_scene.is_manim(_scene(data, args.scene)):
        return _scaffold_manim(project, _scene(data, args.scene))
    if storyboard.is_video(_scene(data, args.scene)):
        return _scaffold_video(project, _scene(data, args.scene))
    if storyboard.is_presenter(_scene(data, args.scene)):
        return _scaffold_presenter(project, _scene(data, args.scene))
    _ensure_node()
    try:
        out = scenes.scaffold(project, _scene(data, args.scene), config.NODE_DIR)
    except scenes.SceneError as e:
        config.error(str(e))
    print(out / "index.html")
    print(out / "brief.md")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    project = _project(args)
    seed = getattr(args, "seed", None)
    model = getattr(args, "model", None)
    data = _valid(project)
    if storyboard.is_clip(_scene(data, args.scene)):
        config.error(clip.refuse(args.scene, "render"))
    if manim_scene.is_manim(_scene(data, args.scene)):
        return _render_manim(project, _scene(data, args.scene))
    if storyboard.is_video(_scene(data, args.scene)):
        return _render_video(project, _scene(data, args.scene), seed, model)
    if storyboard.is_presenter(_scene(data, args.scene)):
        return _render_presenter(project, _scene(data, args.scene), seed, model)
    if seed is not None or model is not None:
        config.error("--seed and --model apply only to a video or presenter scene (`Engine: video`, `Engine: presenter`)")
    # A scene switched from manim to html has a latest version with no page.
    latest = state.latest_scene(project, args.scene)
    if latest is not None and not (latest / "index.html").is_file():
        config.error(f"scene {args.scene}: latest version {latest.name} has no index.html; run `scaffold` first")
    _ensure_node()
    try:
        out = scenes.render(project, _scene(data, args.scene), config.NODE_DIR)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    print(out.parent / "contact.png")
    return 0


def _cmd_clip(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    try:
        out = clip.import_clip(project, _scene(data, args.scene), Path(args.file).expanduser())
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    print(out.parent / "contact.png")
    return 0


def _cmd_frames(args: argparse.Namespace) -> int:
    project = _project(args)
    try:
        times = [float(t) for t in args.at.split(",") if t.strip()]
    except ValueError:
        config.error("--at takes comma-separated seconds, e.g. 3.2,7.5")
    try:
        for p in scenes.frames(project, args.scene, times, args.version):
            print(p)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    return 0


def _cmd_music(args: argparse.Namespace) -> int:
    project = _project(args)
    _valid(project)
    spec = settings.get()["music"]
    if not spec.get("file"):
        config.error(f"no music: make a track with the music skill and set `music.file` in "
                     f"{project / settings.PROJECT_FILE} (without it, `assemble` makes a voice-only film)")
    src = project / Path(spec["file"]).expanduser()
    try:
        out = music.import_file(project, src)
    except FileNotFoundError:
        config.error(f"music file {src} not found")
    print(out)
    _audio_warnings(out, str(out.relative_to(project)))
    return 0


def _cmd_length(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    durations = music.voice_durations(project, data)
    clips = music.clip_durations(project, data)
    narrated = [s for s in storyboard.scenes(data) if storyboard.narrated(s)]
    missing = len(narrated) - len(durations)
    if missing:
        config.warn(f"{missing} scene(s) have no narration yet; the lengths are short")
    if len(clips) < len(storyboard.scenes(data)) - len(narrated):
        config.warn("clip scene(s) without narration have no imported clip yet; the music length is short")
    print(f"narration: {sum(durations):.1f} s" + (" (narrated clip scenes: at least their clip)"
                                                    if any(storyboard.is_clip(s) for s in narrated) else ""))
    if clips:
        print(f"clips without narration: {sum(clips):.1f} s")
    print(f"music: {music.target_seconds(durations + clips)} s")
    return 0


def _cmd_assemble(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    # Each source track on its own: in the mixed film a defect in ducked music
    # or in one channel is too small to find.
    try:
        tracks = mix.sources(project, data, args.music)
    except Exception:
        tracks = []  # assemble reports a missing scene or music version
    for t in tracks:
        _audio_warnings(t, str(t.relative_to(project)))
    try:
        out = mix.assemble(project, data, args.music, _brand_dir(args))
    except (mix.AssembleError, media.ToolError, FileNotFoundError) as e:
        config.error(str(e))
    print(out)
    return 0


def _cmd_audiocheck(args: argparse.Namespace) -> int:
    if args.file:
        tracks = [Path(f).expanduser() for f in args.file]
        base = None
    else:
        base = _project(args)
        try:
            tracks = mix.film_sources(base, args.film) if args.film else mix.sources(base, _valid(base))
        except (mix.AssembleError, OSError, KeyError, ValueError) as e:
            config.error(f"cannot list the tracks: {e}")
    flagged = 0
    for t in tracks:
        name = str(t.relative_to(base)) if base else str(t)
        if not t.is_file():
            config.error(f"{name} not found")
        try:
            found = audiocheck.check(t)
        except media.ToolError as e:
            config.error(f"{name}: {e}")
        if len(tracks) > 1 or base:
            print("\n".join(f"{name} {line}" for line in found) if found else f"{name} clean")
        else:
            print("\n".join(found) if found else "audio: clean")
        flagged += bool(found)
    return 1 if flagged else 0


def _cmd_credit(args: argparse.Namespace) -> int:
    src = Path(args.file).expanduser()
    if not src.is_file():
        config.error(f"{src} not found")
    author = authors(args.author)
    if not author:
        config.error("no author: pass --author NAME (repeat it for several authors)")
    out = Path(args.out).expanduser() if args.out else src.with_name(f"{src.stem}.credit{src.suffix}")
    try:
        b = brand.resolve(args.brand) if args.brand else None
        print(credit.credit_file(src, out, author, b))
    except (media.ToolError, ValueError) as e:
        config.error(str(e))
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    try:
        lines = scenes.setup(config.NODE_DIR, config.NODE_SRC)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print("\n".join(lines))
    print(f"ready: {config.NODE_DIR / 'node_modules'}")
    return 0


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def play_commands(paths: list[Path], system: str | None = None) -> list[list[str]]:
    """The commands for `play` under the OS `system` (`platform.system()`, default this one). On macOS
    one `open -a` command per application: images in `play.image_app`, other files in `play.app`. Elsewhere
    one `xdg-open` command per file, which opens it in the desktop's default application."""
    if (system or platform.system()) != "Darwin":
        return [["xdg-open", str(p)] for p in paths]
    s = settings.get()["play"]
    images = [str(p) for p in paths if p.suffix.lower() in IMAGE_SUFFIXES]
    media = [str(p) for p in paths if p.suffix.lower() not in IMAGE_SUFFIXES]
    return [["open", "-a", app, *files] for app, files in ((s["image_app"], images), (s["app"], media)) if files]


def _cmd_play(args: argparse.Namespace) -> int:
    paths = [Path(f).expanduser() for f in args.files]
    for path in paths:
        if not path.exists():
            config.error(f"{path} not found")
    return max(subprocess.run(cmd).returncode for cmd in play_commands(paths))


def _cmd_critic(args: argparse.Namespace) -> int:
    _project(args)
    c = settings.get().get("critic") or {}
    if "model" in c and c["model"] is None:
        print("off")
        return 0
    from ai_models import config as ai_config
    from ai_models.errors import AIModelsError

    try:
        print(ai_config.resolve(c.get("model"), "film_critic"))
    except AIModelsError as e:
        config.error(str(e))
    return 0


BRAND_HELP = "The brand folder the brand skill reports"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="short-video", description="Narrated short videos from PNG images.")
    sub = p.add_subparsers(dest="command", required=True)

    def project_cmd(name: str, help: str) -> argparse.ArgumentParser:
        c = sub.add_parser(name, help=help)
        c.add_argument("-p", "--project", help="Project folder path; default: current dir")
        return c

    c = sub.add_parser("init", help="Create a project, copy the PNGs if given, write settings.yaml and "
                       "storyboard.md (or storyboard.json)")
    c.add_argument("project", help="Path of the new project folder (created if missing)")
    c.add_argument("--images", help="Folder with the PNGs, one image scene each (optional)")
    c.add_argument("--source", help="Topic or source text file, copied to sources/")
    c.add_argument("--json", action="store_true", help="Write storyboard.json instead of storyboard.md")
    c.set_defaults(func=_cmd_init)

    c = project_cmd("validate", "Validate the storyboard and estimate length")
    c.add_argument("--brand", metavar="DIR", help=BRAND_HELP)
    c.set_defaults(func=_cmd_validate)

    project_cmd("storyboard", "Print the storyboard as storyboard.json stores it").set_defaults(func=_cmd_storyboard)
    project_cmd("status", "Print per scene whether it needs a new voice recording or render (JSON)").set_defaults(
        func=_cmd_status)

    c = project_cmd("script", "Write each scene's narration script for the voiceover skill")
    c.add_argument("--scene", action="append", help="Write this scene's script again (repeatable)")
    c.set_defaults(func=_cmd_script)

    c = project_cmd("voice", "Import narration voiced with the voiceover skill as the next voice version")
    c.add_argument("--scene", action="append", help="Import this scene (repeatable); default: every scene with "
                   "none yet whose sources/narration/<scene>/ is voiced")
    c.add_argument("--src", help="Voiced directory to import (default: sources/narration/<scene>/)")
    c.set_defaults(func=_cmd_voice)

    c = project_cmd("scaffold", "Create the next version of a scene's composition")
    c.add_argument("--scene", required=True)
    c.set_defaults(func=_cmd_scaffold)

    c = project_cmd("render", "Render the latest version of a scene")
    c.add_argument("--scene", required=True)
    c.add_argument("--seed", type=int, help="Seed of the video model (a scene with `Engine: video`)")
    c.add_argument("--model", help="Model id <provider>:<model> of the ai_models config; replaces task `video` "
                   "(`Engine: video`) or `presenter` (`Engine: presenter`)")
    c.set_defaults(func=_cmd_render)

    c = project_cmd("clip", "Import a video as the next version of a clip scene (`Engine: clip`)")
    c.add_argument("--scene", required=True)
    c.add_argument("file", metavar="FILE", help="Video at the `video:` size and fps")
    c.set_defaults(func=_cmd_clip)

    c = project_cmd("frames", "Extract full-size frames from a rendered scene")
    c.add_argument("--scene", required=True)
    c.add_argument("--at", required=True, help="Comma-separated times in seconds, e.g. 3.2,7.5")
    c.add_argument("--version", help="Scene version, e.g. v2 (default: latest rendered)")
    c.set_defaults(func=_cmd_frames)

    c = project_cmd("music", "Import music.file as the next music version")
    c.set_defaults(func=_cmd_music)

    project_cmd("length", "Print the narration length and the music length to request").set_defaults(func=_cmd_length)
    project_cmd("critic", "Print the film critic's model, or `off`").set_defaults(func=_cmd_critic)

    c = project_cmd("assemble", "Assemble the film as the next film version")
    c.add_argument("--music", help="Music version, e.g. v2 (default: latest)")
    c.add_argument("--brand", metavar="DIR", help=BRAND_HELP + "; required when `brand:` is set")
    c.set_defaults(func=_cmd_assemble)

    c = sub.add_parser("credit", help="Add the creator caption and metadata to an existing MP4")
    c.add_argument("file", help="Input MP4")
    c.add_argument("-o", "--out", help="Output file (default: <name>.credit.mp4 next to the input)")
    c.add_argument("--author", action="append", required=True,
                   help="Name to credit (repeat it for several authors)")
    c.add_argument("--brand", metavar="DIR", help=BRAND_HELP + "; its logo goes beside the caption")
    c.set_defaults(func=_cmd_credit)

    c = sub.add_parser("audiocheck", help="Find high-frequency bursts and clicks in audio files; with no "
                       "file, in each track the next film (or --film vN) is mixed from")
    c.add_argument("file", nargs="*", help="Audio or video files (default: the project's tracks)")
    c.add_argument("-p", "--project", help="Project folder path; default: current dir")
    c.add_argument("--film", help="Film version whose tracks to check, e.g. v11 (default: the next assemble)")
    c.set_defaults(func=_cmd_audiocheck)

    sub.add_parser("setup", help="npm ci, render browser, hyperframes doctor").set_defaults(func=_cmd_setup)

    c = sub.add_parser("play", help="Open images and media files in the applications set under `play:` in assets/settings.yaml")
    c.add_argument("files", nargs="+", metavar="FILE")
    c.set_defaults(func=_cmd_play)

    routes.command(sub, ROUTE_TASKS)
    return p


def main() -> None:
    config.load_settings()
    args = _build_parser().parse_args()
    sys.exit(args.func(args))
