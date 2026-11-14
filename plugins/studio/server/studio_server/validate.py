"""Checks of the requests the page sends to `POST /api/request`, per action.

A checked request keeps every field the page sent; paths are replaced by their resolved form.
"""

from __future__ import annotations

import re
from pathlib import Path

from .deck import ASSEMBLY, slide_count, slide_images, versions_used
from .paths import HttpError, inside, positive, read_json, resolve_abs
from .projects import AUTONOMY, PROJECT_FILE, kind_named, project_path
from .video import (
    AUDIO_SUFFIXES,
    check_film,
    check_voice,
    default_film,
    film_of,
    films_of,
    has_picture,
    music_of,
    music_used,
    read_storyboard,
    refuse_markdown,
    review_of,
    scene_ids,
    scene_images,
    scene_named,
    scenes_of,
)

SHAPES = ("1:1", "4:3", "16:9", "9:16")
# image-gen tiers, passed as `--tier`: config tasks image (image_edit with references), image_best,
# image_multi_ref.
MODELS = ("best", "fast", "multi-ref")
MARK_KINDS = ("box", "point", "loop")
# Actions of each workspace skill, for every kind whose skill it is; a skill missing here takes no request but
# `message`.
ACTIONS = {
    "images": ("generate", "change", "variations", "other-styles", "assemble", "message"),
    "videos": ("storyboard", "use-style", "style-samples", "change", "variations", "other-styles", "add-scene",
                    "remake-scene", "music", "own-music", "voice-sample", "make-film", "review", "fix", "phone", "message"),
}
# Actions only some kinds take.
KIND_ACTIONS = {"assemble": ("slide",)}
# The shape of every slide of a deck.
SLIDE_SHAPE = "16:9"
# The `style` of a generate of one slide: the deck's style.
DECK_STYLE = "auto"
# The `style` of a style-samples request.
SAMPLE_STYLES = ("auto", "invent")


def _fail(message: str) -> HttpError:
    return HttpError(400, message)


def _str(req: dict, key: str, empty: bool = True) -> str:
    v = req.get(key)
    if not isinstance(v, str) or (not empty and not v.strip()):
        raise _fail(f"{key} must be a {'' if empty else 'non-empty '}string")
    return v


_int = positive


def _choice(req: dict, key: str, choices: tuple[str, ...]) -> str:
    v = req.get(key)
    if v not in choices:
        raise _fail(f"{key} must be one of {', '.join(choices)}")
    return v


def _str_list(req: dict, key: str) -> list[str]:
    v = req.get(key)
    if not isinstance(v, list) or not all(isinstance(s, str) and s.strip() for s in v):
        raise _fail(f"{key} must be a list of non-empty strings")
    return v


def _fraction(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


def _mark(m: object) -> None:
    if not isinstance(m, dict):
        raise _fail("each mark must be an object")
    n = m.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise _fail("mark n must be a positive integer")
    if not isinstance(m.get("comment"), str):
        raise _fail(f"mark {n}: comment must be a string")
    kind = m.get("kind")
    if kind not in MARK_KINDS:
        raise _fail(f"mark {n}: kind must be one of {', '.join(MARK_KINDS)}")
    keys = {"box": ("x", "y", "w", "h"), "point": ("x", "y"), "loop": ()}[kind]
    if not all(_fraction(m.get(k)) for k in keys):
        raise _fail(f"mark {n}: {', '.join(keys)} must be fractions between 0 and 1")
    if kind == "loop":
        pts = m.get("points")
        if not isinstance(pts, list) or not pts or not all(
                isinstance(p, list) and len(p) == 2 and all(_fraction(c) for c in p) for p in pts):
            raise _fail(f"mark {n}: points must be a non-empty list of [x, y] fractions")


def _version(req: dict, project: Path) -> int:
    n = _int(req, "version")
    if not (project / f"v{n}.png").is_file():
        raise _fail(f"version {n} has no image in {project}")
    return n


def _marks_file(req: dict, key: str, project: Path, n: int, kind: str) -> str:
    """Resolves `req[key]`, which must be an existing `marks/v<n>-<kind>-<k>.png` of the image directory `project`
    (a project, or a deck's slide directory); returns k."""
    path = resolve_abs(req.get(key), key)
    match = re.fullmatch(rf"v{n}-{kind}-([1-9][0-9]*)\.png", path.name)
    if path.parent != project / "marks" or not match or not path.is_file():
        raise _fail(f"{key} must be an existing {project / 'marks' / f'v{n}-{kind}-<k>.png'}")
    req[key] = str(path)
    return match.group(1)


def check_request(req: object, root: Path) -> dict:
    """The checked request (a new dict); HttpError 400 for a request the page must not send."""
    if not isinstance(req, dict):
        raise _fail("a request must be a JSON object")
    req = dict(req)
    req.pop("id", None)
    req.pop("time", None)
    kind = kind_named(req.get("kind"))
    # `skill` is the kind's workspace skill: filled in when missing or null, refused when it names another.
    if req.get("skill") is None:
        req["skill"] = kind.skill
    elif req["skill"] != kind.skill:
        raise _fail(f"skill must be {kind.skill} for kind {kind.id}")
    action = req.get("action")
    actions = tuple(a for a in ACTIONS.get(kind.skill, ("message",)) if kind.id in KIND_ACTIONS.get(a, (kind.id,)))
    if action not in actions:
        raise _fail(f"action must be one of {', '.join(actions)} for {kind.id}")
    deck, video = kind.id == "slide", kind.id == "short-video"
    if not deck and req.get("slide") is not None:
        raise _fail(f"slide is only for slide decks, not {kind.id}")
    if not video and req.get("scene") is not None:
        raise _fail(f"scene is only for short-video projects, not {kind.id}")

    if action == "message":
        _str(req, "text", empty=False)
        if req.get("project") is not None:
            project = project_path(root, req["project"], kind)
            req["project"] = str(project)
            # A message about one slide of a deck, or one scene of a film, names an existing one.
            if deck and req.get("slide") is not None:
                slide_images(project, req)
            if video and req.get("scene") is not None:
                scene_named(project, req)
        else:
            if req.get("slide") is not None or req.get("scene") is not None:
                raise _fail("a message without a project names no slide or scene")
            req["project"] = None
        return req
    if video:
        return _check_video(req, root, kind, action)

    # A generate with project null starts a new project, created by the server once the request is accepted.
    new = action == "generate" and req.get("project") is None
    project = None if new else project_path(root, req.get("project"), kind)
    req["project"] = None if new else str(project)
    # The image directory a version-level action works in: the project, or the deck's slide directory.
    images = project
    if deck and action in ("change", "variations", "other-styles"):
        images = slide_images(project, req)
    if action == "generate":
        adding = False
        if deck and req.get("slide") is not None:
            if new:
                raise _fail("a new deck is made with slide null")
            slide_images(project, req, new=True)
            adding = req["slide"] == slide_count(project) + 1
            # A slide is made in the deck's style; the agent reads it from the slides' sidecars.
            if req.get("style") != DECK_STYLE:
                raise _fail(f"style must be {DECK_STYLE!r} on a generate of one slide (the deck's style)")
        elif deck:
            req["slide"] = None
        _str(req, "brief", empty=not new and not adding)
        if new:
            req["autonomy"] = req.get("autonomy", AUTONOMY[0])
            _choice(req, "autonomy", AUTONOMY)
        refs = req.get("refs")
        if not isinstance(refs, list):
            raise _fail("refs must be a list of absolute paths")
        resolved = []
        for r in refs:
            p = resolve_abs(r, "each ref")
            if not inside(p, root) or not p.is_file():
                raise _fail(f"ref {r} is not a file inside the projects root")
            resolved.append(str(p))
        req["refs"] = resolved
        if req.get("brand") is not None:
            _str(req, "brand", empty=False)
        _choice(req, "shape", (SLIDE_SHAPE,) if deck else SHAPES)
        _choice(req, "model", MODELS)
        # A deck's generate may leave the number of slides to the agent.
        if not (deck and req["slide"] is None and req.get("count") is None):
            _int(req, "count")
        _str(req, "style", empty=False)
    elif action in ("change", "variations", "other-styles"):
        _check_version_action(req, images, action)
    elif action == "assemble":
        if req.get("slide") is not None:
            raise _fail("assemble acts on the whole deck and names no slide")
        _choice(req, "assembly", ASSEMBLY)
        # The slide versions used, fixed when the request is accepted: each slide's chosen version.
        req["versions"] = versions_used(project, read_json(project / PROJECT_FILE))
    return req


def _check_version_action(req: dict, images: Path, action: str) -> None:
    """The fields of a change, variations or other-styles of a version in the image directory `images` (a project,
    a deck's slide directory or a scene's `images/<scene>/`)."""
    if action == "change":
        n = _version(req, images)
        marks = req.get("marks")
        if not isinstance(marks, list):
            raise _fail("marks must be a list")
        for m in marks:
            _mark(m)
        note = _str(req, "note")
        if not marks and not note.strip():
            raise _fail("a change needs a mark or a note")
        if not marks and req.get("marked") is None and req.get("mask") is None:
            req["marked"] = req["mask"] = None
            return
        k = _marks_file(req, "marked", images, n, "marked")
        if _marks_file(req, "mask", images, n, "mask") != k:
            raise _fail(f"mask must be {images / 'marks' / f'v{n}-mask-{k}.png'}, the mask of marked")
    elif action == "variations":
        _version(req, images)
        _int(req, "count")
    elif action == "other-styles":
        _version(req, images)
        _str_list(req, "styles")


def _files_in(req: dict, key: str, directory: Path | None, direct: bool = False) -> list[str]:
    """`req[key]`, a list of absolute paths of files inside `directory` (directly in it with `direct`; None: no
    directory, so the list must be empty), resolved."""
    v = req.get(key)
    if not isinstance(v, list):
        raise _fail(f"{key} must be a list of absolute paths")
    out = []
    for item in v:
        p = resolve_abs(item, f"each of {key}")
        ok = directory is not None and p.is_file() and (p.parent == directory if direct else inside(p, directory))
        if not ok:
            raise _fail(f"{item} is not a file in {directory if directory is not None else f'{key}/ of the project'}")
        out.append(str(p))
    return out


def _check_video(req: dict, root: Path, kind, action: str) -> dict:
    """The checks of a short-video request other than `message`. The server adds `film` to remake-scene, music,
    make-film and fix."""
    # A storyboard with project null starts a new project, created by the server once the request is accepted.
    new = action == "storyboard" and req.get("project") is None
    project = None if new else project_path(root, req.get("project"), kind)
    req["project"] = None if new else str(project)
    if project is not None:
        refuse_markdown(project)
    meta = read_json(project / PROJECT_FILE) if project is not None else None
    meta = meta if isinstance(meta, dict) else {}
    film = film_of(meta)
    if action == "storyboard":
        _str(req, "brief", empty=False)
        if new:
            req["autonomy"] = req.get("autonomy", AUTONOMY[0])
            _choice(req, "autonomy", AUTONOMY)
        req["refs"] = _files_in(req, "refs", project / "refs" if project else None)
        req["sources"] = _files_in(req, "sources", project / "sources" if project else None)
        _str(req, "style", empty=False)
        req["film"] = check_film(project, film if project else default_film(), req.get("film"), whole=True)
        if "make_film" in req and not isinstance(req["make_film"], bool):
            raise _fail("make_film must be true or false")
    elif action == "use-style":
        if (req.get("version") is None) == (req.get("style") is None):
            raise _fail("use-style takes exactly one of version and style")
        if req.get("version") is not None:
            n = _int(req, "version")
            samples = meta.get("samples")
            if not isinstance(samples, dict) or not isinstance(samples.get("versions"), list):
                raise _fail("the project has no style samples")
            if n not in samples["versions"]:
                raise _fail(f"version {n} is not one of the samples {samples['versions']}")
            if samples.get("scene") not in scene_ids(project):
                raise _fail(f"the samples' scene {samples.get('scene')!r} is no longer a scene of the storyboard")
        else:
            _str(req, "style", empty=False)
    elif action == "style-samples":
        _choice(req, "style", SAMPLE_STYLES)
        if not any(has_picture(sc) for sc in scenes_of(read_storyboard(project))):
            raise _fail("no scene of the storyboard has a picture to draw the samples on")
    elif action in ("change", "variations", "other-styles"):
        _check_version_action(req, scene_images(project, req), action)
    elif action == "add-scene":
        if read_storyboard(project) is None:
            raise _fail("add-scene needs a storyboard")
        if req.get("after") is not None and req["after"] not in scene_ids(project):
            raise _fail("after must be the id of a scene in the storyboard, or null for the end")
        _str(req, "text", empty=False)
    elif action == "remake-scene":
        scene_named(project, req)
        req["film"] = film
    elif action == "music":
        _str(req, "brief", empty=False)
        req["film"] = film
    elif action == "own-music":
        req["file"] = _files_in({"file": [req.get("file")]}, "file", project / "sources", direct=True)[0]
        if Path(req["file"]).suffix.lower() not in AUDIO_SUFFIXES:
            raise _fail(f"file must have one of the suffixes {', '.join(AUDIO_SUFFIXES)}")
    elif action == "voice-sample":
        check_voice(req.get("voice"))
    elif action == "make-film":
        _check_film_ready(project, meta, film)
        req["film"] = film
    elif action in ("phone", "review", "fix"):
        n = _int(req, "version")
        if n not in [f["n"] for f in films_of(project)]:
            raise _fail(f"version {n} is not a complete film of {project}")
        if action == "fix":
            _check_film_ready(project, meta, film)
            _check_fix(req, project, n)
            req["film"] = film
    return req


def _check_film_ready(project: Path, meta: dict, film: dict) -> None:
    """Refuses a request that assembles a film (make-film, fix) on a project that cannot make one: no scene, style
    samples waiting, or own music without a track."""
    if not scene_ids(project):
        raise _fail("the storyboard has no scene")
    if meta.get("samples") is not None:
        raise _fail("the film's style is not chosen yet (samples are waiting)")
    if film["music"]["mode"] == "own" and music_used(film, music_of(project)) is None:
        raise _fail("the film's own music has no track yet")


def _check_fix(req: dict, project: Path, n: int) -> None:
    """The fields of a fix of film n: `findings`, distinct numbers `k` of its review.json, and `note`; at least one
    finding or a non-blank note."""
    findings = req.get("findings")
    if not isinstance(findings, list) or not all(isinstance(k, int) and not isinstance(k, bool) for k in findings):
        raise _fail("findings must be a list of finding numbers k")
    if len(set(findings)) != len(findings):
        raise _fail("findings must not repeat a finding")
    note = _str(req, "note")
    if not findings and not note.strip():
        raise _fail("a fix needs a finding or a note")
    if not findings:
        return
    review = review_of(project / "film" / f"v{n}")
    if review is None:
        raise _fail(f"film {n} has no review.json")
    listed = review.get("findings")
    listed = [f.get("k") for f in listed if isinstance(f, dict)] if isinstance(listed, list) else []
    missing = [k for k in findings if k not in listed]
    if missing:
        raise _fail(f"findings {missing} are not in the review of film {n}")
