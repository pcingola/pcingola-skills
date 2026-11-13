"""Checks of the requests the page sends to `POST /api/request`, per action.

A checked request keeps every field the page sent; paths are replaced by their resolved form.
"""

from __future__ import annotations

import re
from pathlib import Path

from .deck import ASSEMBLY, slide_count, slide_images, versions_used
from .paths import HttpError, inside, positive, read_json, resolve_abs
from .projects import AUTONOMY, PROJECT_FILE, kind_named, project_path

SHAPES = ("1:1", "4:3", "16:9", "9:16")
# image-gen tiers, passed as `--tier`: config tasks image (image_edit with references), image_best,
# image_multi_ref.
MODELS = ("best", "fast", "multi-ref")
# Model names of earlier pages, kept in project settings and sidecars, and the tier each maps to.
LEGACY_MODELS = {"gpt-image-2": "best", "nano-banana-pro": "multi-ref", "nano-banana-2": "fast"}
MARK_KINDS = ("box", "point", "loop")
# Actions of each workspace skill, for every kind whose skill it is; a skill missing here takes no request but
# `message`.
ACTIONS = {
    "images": ("generate", "change", "variations", "other-styles", "assemble", "message"),
}
# Actions only some kinds take.
KIND_ACTIONS = {"assemble": ("slide",)}
# The shape of every slide of a deck.
SLIDE_SHAPE = "16:9"
# The `style` of a generate of one slide: the deck's style.
DECK_STYLE = "auto"


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
    deck = kind.id == "slide"
    if not deck and req.get("slide") is not None:
        raise _fail(f"slide is only for slide decks, not {kind.id}")

    if action == "message":
        _str(req, "text", empty=False)
        if req.get("project") is not None:
            project = project_path(root, req["project"], kind)
            req["project"] = str(project)
            # A message about one slide of a deck names an existing slide.
            if deck and req.get("slide") is not None:
                slide_images(project, req)
        else:
            if req.get("slide") is not None:
                raise _fail("a message without a project names no slide")
            req["project"] = None
        return req

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
        _choice(req, "model", MODELS + tuple(LEGACY_MODELS))
        # A deck's generate may leave the number of slides to the agent.
        if not (deck and req["slide"] is None and req.get("count") is None):
            _int(req, "count")
        _str(req, "style", empty=False)
    elif action == "change":
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
            return req
        k = _marks_file(req, "marked", images, n, "marked")
        if _marks_file(req, "mask", images, n, "mask") != k:
            raise _fail(f"mask must be {images / 'marks' / f'v{n}-mask-{k}.png'}, the mask of marked")
    elif action == "variations":
        _version(req, images)
        _int(req, "count")
    elif action == "other-styles":
        _version(req, images)
        _str_list(req, "styles")
    elif action == "assemble":
        if req.get("slide") is not None:
            raise _fail("assemble acts on the whole deck and names no slide")
        _choice(req, "assembly", ASSEMBLY)
        # The slide versions used, fixed when the request is accepted: each slide's chosen version.
        req["versions"] = versions_used(project, read_json(project / PROJECT_FILE))
    return req
