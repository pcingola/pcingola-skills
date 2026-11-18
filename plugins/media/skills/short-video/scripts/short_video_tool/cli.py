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
    screencast Compose screen recordings and screenshots into a clip from a
               YAML shot list (`screencast`), for `clip`.
    frames     Extract full-size frames of a rendered scene at given times.
    stills     PNGs of an HTML scene's page at given times, from the page in the
               render browser (no render needed); a marked copy, a contact sheet.
    check      Run the static checks of `render` on an HTML scene's page.
    html       Write the film as one standalone film.html that plays every
               scene's latest page: film/html/v<N>/film.html.
    refs       Extract frames, contact sheets, palette and motion curve of
               reference videos and images into refs/.
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
    particle-text
               Write the particle targets and glyph texture of a text block
               from a font file, for a particle-text page (kit/particles.js).

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

`scaffold` and `render` of a scene with `World:` act on its whole world
(`world`): `scaffold` writes the next `worlds/<name>/v<N>/`, `render` renders
it once and writes the next version of every scene of the world.

`dispatch` chooses the engine of `scaffold` and `render`. Each handler parses
its arguments, calls the module function that does the work, prints its
result and returns the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from ai_models import routes
from plugin_settings import config as plugin_config

from . import audiocheck, brand, clip, config, credit, media, mix, music, narration, scenes, settings
from . import dispatch, film_html, pages, projects, refs, status, stills, storyboard

# The tasks of video and presenter scenes; `routes` prints their rows.
ROUTE_TASKS = ("video", "presenter")


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


def _ensure_node(node_dir: Path) -> None:
    try:
        scenes.ensure_node(node_dir, config.NODE_SRC)
    except scenes.SceneError as e:
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
    try:
        made = projects.create(project, Path(args.images).expanduser() if args.images else None,
                               Path(args.source).expanduser() if args.source else None,
                               args.json, args.silent, args.length)
    except (projects.ProjectError, storyboard.StoryboardError) as e:
        config.error(str(e))
    print(made.project)
    print(f"  {settings.PROJECT_FILE}")
    print(f"  {made.storyboard_file}")
    for name in made.images:
        print(f"  images/{name}")
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


def _cmd_script(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    try:
        parts = narration.write_scripts(project, data, args.scene)
    except (storyboard.StoryboardError, narration.NarrationError) as e:
        config.error(str(e))
    for part in parts:
        print(part.path)
        if part.voice_line is not None:
            print("  " + part.voice_line)
    if not parts:
        print("every scene has narration; name scenes with --scene to write their scripts again")
    return 0


def _cmd_voice(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    try:
        targets = narration.voice_targets(project, data, args.scene)
    except (storyboard.StoryboardError, narration.NarrationError) as e:
        config.error(str(e))
    for s in targets:
        try:
            out = narration.import_voice(project, data, s, Path(args.src).expanduser() if args.src else None)
        except narration.NarrationError as e:
            config.error(str(e))
        print(out / "narration.wav")
        _audio_warnings(out / "narration.wav", str((out / "narration.wav").relative_to(project)))
    if not targets:
        print("nothing to import: voice `sources/narration/<scene>/script.txt` (or every "
              "`sources/narration/<scene>/p<k>/script.txt`) with the voiceover skill first, "
              "or name scenes with --scene")
    return 0


def _cmd_scaffold(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    try:
        files = dispatch.scaffold(project, data, args.scene, getattr(args, "node_dir", None),
                                  getattr(args, "refresh", False), getattr(args, "estimate", False))
    except (storyboard.StoryboardError, scenes.SceneError) as e:
        config.error(str(e))
    for f in files:
        print(f)
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    try:
        outs = dispatch.render(project, data, args.scene, getattr(args, "node_dir", None),
                               getattr(args, "manim_env", None), getattr(args, "seed", None),
                               getattr(args, "model", None))
    except (storyboard.StoryboardError, scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    for out in outs:
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


def _cmd_screencast(args: argparse.Namespace) -> int:
    from . import screencast
    scene = None
    if args.scene:
        project = _project(args)
        scene = _scene(_valid(project), args.scene)
        if not storyboard.is_clip(scene):
            config.error(f"scene {args.scene} is not a clip scene; give it `Engine: clip` in the storyboard")
        out = Path(args.out).expanduser() if args.out else project / "sources" / f"{args.scene}-screencast.mp4"
    else:
        if not args.out:
            config.error("give -o OUT, or --scene ID to write into the project's sources/")
        project = config.resolve_project(args.project)
        settings.use_project(project if (project / settings.PROJECT_FILE).is_file() else None)
        out = Path(args.out).expanduser()
    shots = Path(args.shots).expanduser()
    try:
        if args.at:
            try:
                times = [float(t) for t in args.at.split(",") if t.strip()]
            except ValueError:
                config.error("--at takes comma-separated seconds, e.g. 0.5,2.1")
            for p in screencast.stills(shots, times, out.with_suffix("")):
                print(p)
            return 0
        screencast.render(shots, out)
    except (screencast.ScreencastError, media.ToolError) as e:
        config.error(str(e))
    print(out)
    if scene is not None:
        if warning := clip.length_warning(project, scene, out):
            config.warn(warning)
        print(f"next: clip --scene {scene['id']} {out}")
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


def _cmd_stills(args: argparse.Namespace) -> int:
    project = _project(args)
    try:
        times = stills.parse_times(args.at)
    except ValueError:
        config.error("--at takes comma-separated seconds, e.g. 3.2,7.5")
    try:
        mark = stills.Mark.parse(args.mark) if args.mark else None
    except ValueError as e:
        config.error(str(e))
    data = _valid(project)
    scene = _scene(data, args.scene)
    try:
        page = pages.scene_page(project, data, scene, args.version)
    except scenes.SceneError as e:
        config.error(str(e))
    _ensure_node(args.node_dir)
    try:
        for p in stills.stills(scene["id"], page, times, args.node_dir, mark, args.sheet):
            print(p)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    _ensure_node(args.node_dir)
    try:
        index, warnings = pages.check(project, data, _scene(data, args.scene), args.node_dir)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    for line in warnings:
        print(line)
    print(f"ok: {index}")
    return 0


def _cmd_html(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _valid(project)
    _ensure_node(args.node_dir)
    try:
        out, warnings = film_html.write(project, data, args.node_dir,
                                        Path(args.out).expanduser() if args.out else None, args.music)
    except (scenes.SceneError, mix.AssembleError, media.ToolError, FileNotFoundError) as e:
        config.error(str(e))
    for w in warnings:
        config.warn(w)
    print(out)
    print(f"  {out.stat().st_size / 1e6:.1f} MB")
    return 0


def _cmd_refs(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser() if args.out else _project(args) / "refs"
    try:
        index = refs.run(Path(args.src), out, args.fps)
    except (refs.RefsError, media.ToolError) as e:
        config.error(str(e))
    print("\n".join(refs.summary(index, out, Path(args.src))))
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
        lines = scenes.setup(args.node_dir, config.NODE_SRC)
    except (scenes.SceneError, media.ToolError) as e:
        config.error(str(e))
    print("\n".join(lines))
    print(f"ready: {args.node_dir / 'node_modules'}")
    return 0


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
# An HTML page (film.html) opens in the default browser.
PAGE_SUFFIXES = {".html", ".htm"}


def play_commands(paths: list[Path], system: str | None = None) -> list[list[str]]:
    """The commands for `play` under the OS `system` (`platform.system()`, default this one). On macOS
    one `open -a` command per application: images in `play.image_app`, other files in `play.app`; HTML pages
    in the default browser (`open`). Elsewhere
    one `xdg-open` command per file, which opens it in the desktop's default application."""
    if (system or platform.system()) != "Darwin":
        return [["xdg-open", str(p)] for p in paths]
    s = settings.get()["play"]
    images = [str(p) for p in paths if p.suffix.lower() in IMAGE_SUFFIXES]
    pages = [str(p) for p in paths if p.suffix.lower() in PAGE_SUFFIXES]
    media = [str(p) for p in paths if p.suffix.lower() not in IMAGE_SUFFIXES | PAGE_SUFFIXES]
    return ([["open", "-a", app, *files] for app, files in ((s["image_app"], images), (s["app"], media)) if files]
            + ([["open", *pages]] if pages else []))


def _cmd_play(args: argparse.Namespace) -> int:
    paths = [Path(f).expanduser() for f in args.files]
    for path in paths:
        if not path.exists():
            config.error(f"{path} not found")
    return max(subprocess.run(cmd).returncode for cmd in play_commands(paths))


def _cmd_critic(args: argparse.Namespace) -> int:
    _project(args)
    from ai_models.errors import AIModelsError

    try:
        model = settings.critic_model()
    except AIModelsError as e:
        config.error(str(e))
    print("off" if model is None else model)
    return 0


def _cmd_particle_text(args: argparse.Namespace) -> int:
    from . import particle_text

    if args.out:
        out = Path(args.out).expanduser()
        project = config.resolve_project(args.project)
        settings.use_project(project if (project / settings.PROJECT_FILE).is_file() else None)
    else:
        if not args.scene:
            config.error("give --scene ID (its latest page version) or --out DIR")
        project = _project(args)
        data = _valid(project)
        try:
            out = pages.scene_page(project, data, _scene(data, args.scene)).dir
        except scenes.SceneError as e:
            config.error(str(e))
    try:
        if args.frame:
            width, height = particle_text.parse_frame(args.frame)
        else:
            v = settings.get()["video"]
            width, height = int(v["width"]), int(v["height"])
        text = particle_text.ParticleText(
            tuple(args.lines), Path(args.font).expanduser(), size=args.size, tracking=args.tracking,
            line_gap=args.line_gap, count=args.count, edge_share=args.edge_share, seed=args.seed,
            width=width, height=height, fov=args.fov, distance=args.distance)
        written = particle_text.write_block(text, out, args.name, args.fit)
    except ValueError as e:
        config.error(str(e))
    for p in written.files:
        print(p)
    for line in written.report():
        print(line, file=sys.stderr)
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
    c.add_argument("--silent", action="store_true", help="A film without narration: silent scenes with `Length:`, "
                   "no title or end template scenes")
    c.add_argument("--length", type=float, metavar="S", help="The film length the user asks for, in seconds: sets "
                   "length.min_seconds and max_seconds in settings.yaml (and, with --silent, the scene Lengths)")
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
    c.add_argument("--refresh", action="store_true",
                   help="HTML scene or world: rewrite brief.md and the timing files of the latest version in place "
                        "(refused once it is rendered); its page and added files stay")
    c.add_argument("--estimate", action="store_true",
                   help="Narrated HTML scene without a world: time the page from the narration's words at "
                        "length.words_per_second instead of a recording (no voice needed; `render` refuses the "
                        "version until a scaffold after `voice`)")
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

    c = project_cmd("screencast", "Compose screen recordings and screenshots into a clip from a YAML shot list")
    c.add_argument("--shots", required=True, metavar="FILE", help="The shot list (references/screencast.md)")
    c.add_argument("--scene", help="A clip scene: write sources/<ID>-screencast.mp4 and print the `clip` step")
    c.add_argument("-o", "--out", help="Output MP4 (default with --scene: sources/<ID>-screencast.mp4)")
    c.add_argument("--at", help="Write PNG frames at these comma-separated clip times instead of the MP4, "
                   "named <OUT without .mp4>_<time>.png")
    c.set_defaults(func=_cmd_screencast)

    c = project_cmd("frames", "Extract full-size frames from a rendered scene")
    c.add_argument("--scene", required=True)
    c.add_argument("--at", required=True, help="Comma-separated times in seconds, e.g. 3.2,7.5")
    c.add_argument("--version", help="Scene version, e.g. v2 (default: latest rendered)")
    c.set_defaults(func=_cmd_frames)

    c = project_cmd("stills", "PNGs of an HTML scene's page at given times, without a render")
    c.add_argument("--scene", required=True)
    c.add_argument("--at", required=True, help="Comma-separated scene times in seconds, e.g. 1.2,3.4")
    c.add_argument("--version", help="Scene version, e.g. v2 (a world scene: world version; default: latest page)")
    c.add_argument("--mark", metavar="X,Y[,W,H]", help="Also write a copy with a red point or rectangle, in frame "
                   "pixels")
    c.add_argument("--sheet", action="store_true", help="Also write one contact sheet of the stills")
    c.set_defaults(func=_cmd_stills)

    c = project_cmd("check", "Run the static checks of render (helpers, timeline, determinism, lint) on a scene's "
                    "latest page")
    c.add_argument("--scene", required=True)
    c.set_defaults(func=_cmd_check)

    c = project_cmd("html", "Write the film as one standalone film.html playing every scene's latest page")
    c.add_argument("--out", metavar="PATH", help="Write film.html here instead of film/html/v<N>/")
    c.add_argument("--music", help="Music version, e.g. v2 (default: as `assemble`)")
    c.set_defaults(func=_cmd_html)

    c = project_cmd("refs", "Frames, contact sheets, palette and motion curve of a reference video or images, "
                    "into the project's refs/")
    c.add_argument("--src", required=True, metavar="FILE_OR_DIR", help="Reference video, image, or a folder of them")
    c.add_argument("--fps", type=float, default=refs.FPS, help="Frames per second to extract (default: 4)")
    c.add_argument("--out", metavar="DIR", help="Output folder (default: <project>/refs)")
    c.set_defaults(func=_cmd_refs)

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

    c = sub.add_parser("particle-text", help="Write <name>_targets.js and <name>_tex.png of a text block for a "
                       "particle-text page (kit/particles.js)")
    c.add_argument("lines", nargs="+", metavar="LINE", help="Text, one argument per centred line")
    c.add_argument("--font", required=True, help="Font file: .woff2, .woff, .ttf or .otf")
    c.add_argument("--name", help="Targets name: PT_TARGETS key and file prefix (default: from the text)")
    c.add_argument("--size", type=float, default=150, help="Font size (em) in frame pixels at --distance "
                   "(default: 150)")
    c.add_argument("--fit", type=float, metavar="F", help="Pick --size so the text is F of the frame width at the "
                   "page's end camera distance, e.g. 0.6")
    c.add_argument("--tracking", type=float, default=0.0, help="Extra letter spacing in em (default: 0)")
    c.add_argument("--line-gap", type=float, default=1.12, help="Line pitch in em (default: 1.12)")
    c.add_argument("--count", type=int, default=24000, help="Particles (default: 24000)")
    c.add_argument("--edge-share", type=float, default=0.34, help="Share of particles on letter outlines "
                   "(default: 0.34)")
    c.add_argument("--seed", type=int, default=1, help="Seed of the particle samples (default: 1)")
    c.add_argument("--frame", metavar="WxH", help="Frame size (default: `video:` of settings.yaml, 1920x1080)")
    c.add_argument("--fov", type=float, default=35, help="Camera vertical field of view, degrees (default: 35)")
    c.add_argument("--distance", type=float, default=20, help="Camera distance at which the text measures "
                   "--size px (default: 20)")
    c.add_argument("-p", "--project", help="Project folder path; default: current dir")
    c.add_argument("--scene", help="Write into this scene's latest page version (a world scene: its world's)")
    c.add_argument("--out", metavar="DIR", help="Write into DIR instead of a scene version")
    c.set_defaults(func=_cmd_particle_text)

    routes.command(sub, ROUTE_TASKS)
    return p


def main(argv: list[str] | None = None, plugin_env_dir: Path | None = None) -> int:
    """Run the command in `argv` (default: `sys.argv[1:]`) and return its exit code; `--help` and argument errors
    return argparse's code. Validates the settings file (exit on an invalid one) and leaves `os.environ` as it is:
    the wrapper path (`__main__`) exports the settings to the environment before it calls `main`.

    A command error, which a handler reports with `config.error` (exit 1), is returned as the exit code.

    `plugin_env_dir` is the plugin environment directory, which places the node directory and the Manim
    environment (`config.env_dirs`); None reads `PLUGIN_ENV_DIR`, as the wrapper short-video.sh sets it. The
    handlers find them as `args.node_dir` and `args.manim_env`."""
    plugin_config()
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if plugin_env_dir is None:
        env_value = os.environ.get("PLUGIN_ENV_DIR")
        plugin_env_dir = Path(env_value) if env_value else None
    dirs = config.env_dirs(plugin_env_dir)
    args.node_dir, args.manim_env = dirs.node_dir, dirs.manim_env
    try:
        return args.func(args)
    except SystemExit as e:
        # A command error (`config.error`: `Error: <msg>` on stderr, then exit 1) is the exit code.
        if e.code is None or isinstance(e.code, int):
            return e.code or 0
        print(e.code, file=sys.stderr)
        return 1
