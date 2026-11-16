"""Short videos: a project of kind `short-video` is a `media:short-video` project directory with Studio's project.json.

The storyboard is `storyboard.json` (the structure media:short-video parses `storyboard.md` into); the page edits it
through `/api/storyboard`, checked here by the same structural rules media:short-video applies when it reads it. The
agent writes `status.json` (each scene's state and the scene object it was computed on); the server compares the
storyboard with it to show each scene's state, and reads the version directories media:short-video writes
(`voice/<scene>/v<N>/`, `scenes/<scene>/v<N>/`, `worlds/<world>/v<N>/`, `music/v<N>/`, `film/v<N>/`,
`film/html/v<N>/`) and the scene pictures in
`images/<scene>/`. Nothing here runs or imports media:short-video.
"""

from __future__ import annotations

import copy
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from plugin_settings import ConfigFileError, load_config

from .deck import versions_of
from .paths import HttpError, log, read_json

DIRECTORY = "short-video"
STORYBOARD = "storyboard.json"
STORYBOARD_MD = "storyboard.md"
STATUS = "status.json"
META = "meta.json"
MANIFEST = "manifest.json"
STUDIO_JSON = "studio.json"
REVIEW_JSON = "review.json"
WORLD_JSON = "world.json"
COMMENTS = "comments"
# The URL prefix of the /scene/ route: a random token per server run, so only a page that read /api/project can name
# a scene file (the route answers cross-site requests, for the sandboxed scene page).
SCENE_PREFIX = f"/scene/{secrets.token_urlsafe(16)}/"
SCENE_ID = re.compile(r"^[a-z0-9_]+$")
VERSION_DIR = re.compile(r"^v([1-9][0-9]*)$")
FILM_HTML = "film.html"
ROOT_TAG = re.compile(r"<[a-zA-Z][^>]*\bdata-composition-id\b[^>]*>")
DATA_DURATION = re.compile(r"""\bdata-duration\s*=\s*["']([0-9]+(?:\.[0-9]+)?)["']""")
SAMPLE_JSON = re.compile(r"^voice-([1-9][0-9]*)\.json$")
SAMPLE_WAV = "narration.wav"
SAMPLE_DIR = re.compile(r"^voice-[1-9][0-9]*$")
PICTURE_FILE = re.compile(r"^v([1-9][0-9]*)\.(?:png|json)$")
# A still of a drawn scene's page: the sidecar `images/<scene>/v<N>.json` names its page version (`page_version`,
# a scene or world version directory) and the still `media:short-video`'s `stills` wrote in its `stills/`.
PAGE_VERSION = re.compile(r"^(?:scenes|worlds)/[a-z0-9_]+/v[1-9][0-9]*$")
STILL_NAME = re.compile(r"^(?:[a-z0-9_]+_)?at_[0-9]+(?:\.[0-9]+)?\.png$")
VERSION_JSON = re.compile(r"^v([1-9][0-9]*)\.json$")

# The storyboard structure, as media:short-video's storyboard check has it.
TOP_KEYS = ("title", "topic", "source", "speakers", "scenes")
SCENE_KEYS = ("id", "template", "image", "brief", "engine", "ambience", "preview", "narration", "beats", "speakers",
              "voices", "world", "length", "show_author")
# Scene keys that change only the assembled film (the creator caption), not the scene's recording or render.
FILM_ONLY_KEYS = ("show_author",)
VOICE_KEYS = ("model", "name", "speed", "style")
# The voice field of an earlier version; `backend_model` maps its values, as media:short-video does.
OLD_VOICE_KEY = "backend"
# The earlier backend that meant config.yaml's `speech` model; every other earlier backend is a provider kind.
SPEECH_BACKEND = "speech"
BACKEND_MOVED = ("Backend (`backend`) became Model (`model`), a speech model id <provider>:<model> of config.yaml: for "
                 "an earlier backend named after a provider kind (kokoro, chatterbox), a model of a provider of that "
                 "kind; for speech, null (config.yaml's tasks.speech)")


def backend_model(backend: object) -> str | None:
    """The model id an earlier voice `backend` maps to: None (config.yaml's `speech` model) for `speech` or a value
    the config cannot map, else the configured speech model of the provider kind of that name
    (`ai_models.speech.model_of_kind`)."""
    from ai_models import AIModelsError, speech

    if not isinstance(backend, str) or backend == SPEECH_BACKEND:
        return None
    try:
        return speech.model_of_kind(backend)
    except AIModelsError:
        return None


ENGINES = ("html", "manim", "video", "presenter", "clip")
# The templates of media:short-video's default settings (`templates:`), which Studio's settings.yaml does not change,
# each with its `show_author` rule: whether the creator caption is drawn over a scene of that template that does not
# set `show_author` itself. tests/unit/studio/test_video.py checks this copy against media:short-video's settings.
TEMPLATE_SHOW_AUTHOR = {"title": False, "summary": True, "end": False}
TEMPLATES = tuple(TEMPLATE_SHOW_AUTHOR)

# Film settings (`film` in project.json).
SPEED = (0.5, 2.0)
MUSIC_MODES = ("made", "own", "none")
VOLUMES = ("quiet", "normal", "louder")
SHAPES = ("16:9", "9:16")
LENGTHS = (30, 60, 120, 180)
FILM_KEYS = ("voice", "music", "shape", "length", "author", "brand", "review", "silent")
FILM_DEFAULTS = {
    "voice": {"model": None, "name": None, "speed": 1.0, "style": None},
    "music": {"mode": "made", "brief": "", "volume": "normal", "version": None},
    "shape": "16:9",
    "length": 60,
    "author": [],
    "brand": None,
    "review": True,
    "silent": False,
}
PHONE_SHAPE = "9:16"
PHONE_LENGTH = 60

AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
SOURCE_SUFFIXES = (".pdf", ".txt", ".md", ".docx", ".pptx", ".xlsx", ".csv", ".html") + AUDIO_SUFFIXES
# A reference video in refs/ of a short-video project, by type, and its largest size: the upload is a base64 data
# URL inside a JSON body of at most 64 MiB.
VIDEO_SUFFIXES = {"video/mp4": (".mp4",), "video/quicktime": (".mov",), "video/webm": (".webm",)}
REF_VIDEO_MAX = 45 * 1024 * 1024

# Requests that write pictures of one scene (named in `scene`), and requests that write pictures of many scenes.
SCENE_PICTURE_ACTIONS = ("change", "variations", "other-styles", "use-still")
FILM_PICTURE_ACTIONS = ("storyboard", "use-style", "style-samples", "add-scene")


def default_authors() -> list[str]:
    """The names of the setting `studio.author` of config.yaml, a new film's "Made by"; [] when it is not set or
    the file is not valid (the error is logged, so the server keeps running)."""
    try:
        return list(load_config().studio.author)
    except ConfigFileError as e:
        log(f"studio.author not read: {e}")
        return []


def default_film() -> dict:
    """The settings of a new film: FILM_DEFAULTS with `author` from the setting `studio.author`."""
    return copy.deepcopy(FILM_DEFAULTS) | {"author": default_authors()}


def is_video(project: Path) -> bool:
    """True for a project of kind `short-video`."""
    return project.parent.name == DIRECTORY


# The storyboard structure check

def normalize(obj: object) -> object:
    """Every string with each run of whitespace collapsed to one space and the ends stripped, recursively, as
    media:short-video reads the storyboard."""
    if isinstance(obj, str):
        return " ".join(obj.split())
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def _text(v: object) -> bool:
    return isinstance(v, str) and bool(v)


def _number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _voice_fields(v: object, label: str, err) -> None:
    if not isinstance(v, dict):
        err(f"{label}: must be an object with any of {', '.join(VOICE_KEYS)}")
        return
    for k, x in v.items():
        if k == OLD_VOICE_KEY:
            err(f"{label}: {BACKEND_MOVED}")
        elif k not in VOICE_KEYS:
            err(f"{label}: unknown key `{k}`; allowed: {', '.join(VOICE_KEYS)}")
        elif x is not None and not (_number(x) if k == "speed" else isinstance(x, str)):
            err(f"{label}: `{k}` must be {'a number' if k == 'speed' else 'a string'} or null")


def check_storyboard(data: object) -> list[str]:
    """Every structural problem of a storyboard, checked on its normalized form; empty when it is valid."""
    out: list[str] = []
    err = out.append
    # The server reads the scene ids as written, so an id must match before whitespace is collapsed too.
    raw = data.get("scenes") if isinstance(data, dict) else None
    for i, s in enumerate(raw if isinstance(raw, list) else []):
        sid = s.get("id") if isinstance(s, dict) else None
        if isinstance(sid, str) and not SCENE_ID.match(sid) and SCENE_ID.match(" ".join(sid.split())):
            err(f"scene {i + 1}: id {sid!r} has whitespace; use lowercase letters, digits and _ only")
    data = normalize(data)
    if not isinstance(data, dict):
        return ["the storyboard must be an object"]
    for k in data:
        if k not in TOP_KEYS:
            err(f"unknown key `{k}`; allowed: {', '.join(TOP_KEYS)}")
    for k in ("title", "topic"):
        if k in data and not isinstance(data[k], str):
            err(f"`{k}` must be a string")
        elif not data.get(k):
            err(f"missing `{k}`")
    if "source" in data and not _text(data["source"]):
        err("`source` must be a path under sources/")
    speakers = data.get("speakers", {})
    if not isinstance(speakers, dict):
        err("`speakers` must be an object of speaker name to voice")
        speakers = {}
    for name, v in speakers.items():
        if not SCENE_ID.match(name):
            err(f"invalid speaker name {name!r}: use lowercase letters, digits and _ only")
        _voice_fields(v, f"speaker {name!r}", err)
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        err("no scenes; add an entry to `scenes`")
        scenes = scenes if isinstance(scenes, list) else []
    seen: set[str] = set()
    for i, s in enumerate(scenes):
        _check_scene(s, i, seen, speakers, err)
    _check_worlds(scenes, err)
    return out


def _check_worlds(scenes: list, err) -> None:
    """The scenes of one world (`world`) follow each other in the storyboard."""
    ended: set[str] = set()
    previous = None
    for s in scenes:
        world = s.get("world") if isinstance(s, dict) else None
        world = world if isinstance(world, str) else None
        if world != previous and previous is not None:
            ended.add(previous)
        if world is not None and world in ended:
            err(f"the scenes of world {world!r} must follow each other in the storyboard")
            ended.discard(world)
        previous = world


def _check_scene(s: object, i: int, seen: set, speakers: dict, err) -> None:
    if not isinstance(s, dict):
        err(f"scene {i + 1}: must be an object")
        return
    sid = s.get("id")
    if not isinstance(sid, str) or not SCENE_ID.match(sid):
        err(f"invalid scene id {sid!r}: use lowercase letters, digits and _ only")
        label = f"scene {i + 1}"
    else:
        label = f"scene {sid!r}"
        if sid in seen:
            err(f"duplicate scene id {sid!r}")
        seen.add(sid)
    for k in s:
        if k not in SCENE_KEYS:
            err(f"{label}: unknown key `{k}`; allowed: {', '.join(SCENE_KEYS)}")
    for k in ("template", "image", "brief", "engine", "preview", "world"):
        if k in s and not isinstance(s[k], str):
            err(f"{label}: `{k}` must be a string")
    engine, template = s.get("engine"), s.get("template")
    html = template is None and engine in (None, "html")
    if isinstance(s.get("world"), str):
        if not SCENE_ID.match(s["world"]):
            err(f"{label}: invalid world name {s['world']!r}: use lowercase letters, digits and _ only")
        if template is not None or "image" in s or not html:
            err(f"{label}: a world scene is an HTML scene without `template` or `image`")
    length = s.get("length")
    if "length" in s:
        if not _number(length) or length <= 0:
            err(f"{label}: `length` must be a positive number of seconds")
        if not html or s.get("narration"):
            err(f"{label}: only an HTML scene without narration has `length`")
    if engine is not None and engine not in ENGINES:
        err(f"{label}: `engine` must be one of {', '.join(ENGINES)}")
    if template is not None:
        if template not in TEMPLATES:
            err(f"{label}: `template` must be one of {', '.join(TEMPLATES)}")
        if engine is not None:
            err(f"{label}: a template scene takes no `engine`")
        if "brief" in s:
            err(f"{label}: a template scene takes no `brief`")
    elif engine not in ("clip", "presenter") and not s.get("brief"):
        err(f"{label}: missing `brief`")
    if s.get("image") == "":
        err(f"{label}: `image` is empty; name a file under images/ or leave it out")
    elif engine == "video" and template is None and "image" not in s:
        err(f"{label}: missing `image`; a scene with `engine` video animates that image")
    elif engine == "presenter" and template is None and "image" not in s:
        err(f"{label}: missing `image`; a scene with `engine` presenter makes the person in that image speak")
    if "ambience" in s:
        if not isinstance(s["ambience"], bool):
            err(f"{label}: `ambience` must be true or false")
        elif engine != "video" or template is not None:
            err(f"{label}: only a scene with `engine` video has `ambience` (the video model's sound track)")
    if "show_author" in s and not isinstance(s["show_author"], bool):
        err(f"{label}: `show_author` must be true or false")
    silent = (engine == "clip" and template is None) or (html and "length" in s)
    narration = s.get("narration", [] if silent else None)
    if not isinstance(narration, list) or not all(_text(x) for x in narration):
        err(f"{label}: `narration` must be a list of non-empty sentences")
        return
    if not narration and not silent:
        err(f"{label}: missing sentences in `narration` (only a scene with `engine` clip or `length` may have "
            "none)")
    n = len(narration)
    beats = s.get("beats", [] if silent else None)
    if not isinstance(beats, list) or len(beats) != n or not all(_text(x) for x in beats):
        err(f"{label}: `beats` must be a list of {n} non-empty strings, one per sentence")
    if "speakers" in s:
        names = s["speakers"]
        if not isinstance(names, list) or len(names) != n:
            err(f"{label}: `speakers` must be a list of {n} speaker names or nulls, one per sentence")
        else:
            for j, sp in enumerate(names):
                if sp is not None and not (isinstance(sp, str) and sp in speakers):
                    err(f"{label} sentence {j + 1}: speaker {sp!r} is not defined in `speakers`")
    if "voices" in s:
        voices = s["voices"]
        if not isinstance(voices, list) or len(voices) != n:
            err(f"{label}: `voices` must be a list of {n} voice objects or nulls, one per sentence")
        else:
            for j, v in enumerate(voices):
                if v is not None:
                    _voice_fields(v, f"{label} sentence {j + 1}", err)


# The storyboard on disk

def storyboard_mtime(project: Path) -> str | None:
    """The modification time of storyboard.json in nanoseconds as a decimal string; None without the file."""
    try:
        return str((project / STORYBOARD).stat().st_mtime_ns)
    except OSError:
        return None


def read_storyboard(project: Path) -> dict | None:
    """storyboard.json, or None when it is missing or not a JSON object."""
    data = read_json(project / STORYBOARD)
    return data if isinstance(data, dict) else None


def scenes_of(storyboard: object) -> list[dict]:
    """The scene objects of a storyboard whose `id` is a scene id, in film order."""
    scenes = storyboard.get("scenes") if isinstance(storyboard, dict) else None
    if not isinstance(scenes, list):
        return []
    return [s for s in scenes if isinstance(s, dict) and isinstance(s.get("id"), str) and SCENE_ID.match(s["id"])]


def show_author(scene: dict) -> bool:
    """Whether the film's creator caption is drawn over a scene: its own `show_author`, else its template's rule
    (`TEMPLATE_SHOW_AUTHOR`), else True; as media:short-video's `storyboard.show_author`."""
    if isinstance(scene.get("show_author"), bool):
        return scene["show_author"]
    return TEMPLATE_SHOW_AUTHOR.get(scene.get("template"), True)


def has_picture(scene: dict) -> bool:
    """Whether a scene has a picture: it names an `image`, or it is a template scene (its picture is the
    background)."""
    return bool(scene.get("image")) or bool(scene.get("template"))


def is_drawn(scene: dict) -> bool:
    """Whether a scene is drawn in its page: an HTML scene (no template, `engine` absent or html) without `image`.
    Its picture versions are stills of its page."""
    return not scene.get("template") and scene.get("engine") in (None, "html") and not scene.get("image")


def is_still(version: dict) -> bool:
    """Whether a picture version is a still of a drawn scene's page: its sidecar names the page version
    (`page_version`, relative to the project) it was taken from."""
    return isinstance(version.get("page_version"), str)


def still_image(project: Path, sidecar: dict) -> Path | None:
    """The PNG a still's sidecar names: `<project>/<page_version>/stills/<still>`, a file reached without a symbolic
    link; None when the sidecar is not a still's or the file is not there."""
    page, still = sidecar.get("page_version"), sidecar.get("still")
    if not (isinstance(page, str) and PAGE_VERSION.match(page) and isinstance(still, str) and STILL_NAME.match(still)):
        return None
    d = project
    for part in [*page.split("/"), "stills"]:
        d = d / part
        if d.is_symlink():
            return None
    f = d / still
    return f if f.is_file() and not f.is_symlink() else None


def scene_pictures(project: Path, directory: Path) -> list[dict]:
    """The picture versions of `images/<scene>/`, newest first: each `v<N>.png` with its sidecar (`versions_of`),
    and each still of the scene's page, whose sidecar names a still that exists (`image` is that still)."""
    pictures = versions_of(directory)
    listed = {v["n"] for v in pictures}
    try:
        names = os.listdir(directory)
    except OSError:
        names = []
    for f in names:
        m = VERSION_JSON.match(f)
        if not m or int(m.group(1)) in listed:
            continue
        data = read_json(directory / f)
        image = still_image(project, data) if isinstance(data, dict) else None
        if image is not None:
            pictures.append({**data, "n": int(m.group(1)), "image": str(image)})
    return sorted(pictures, key=lambda v: v["n"], reverse=True)


def key_scene(scenes: list[dict]) -> str | None:
    """The key scene, on which style samples are made: the first scene with a picture that is not a template scene,
    else the first drawn scene, else the first template scene; None when there is none."""
    for test in (lambda sc: bool(sc.get("image")), is_drawn, lambda sc: bool(sc.get("template"))):
        found = next((sc["id"] for sc in scenes if test(sc)), None)
        if found is not None:
            return found
    return None


def style_sample_versions(project: Path, scene: str) -> list[int]:
    """The N of the stills of `images/<scene>/` that carry a `page_style` object: every style sample made on the
    scene's page, newest first."""
    return [v["n"] for v in scene_pictures(project, project / "images" / scene)
            if is_still(v) and isinstance(v.get("page_style"), dict)]


def picture_file(project: Path, directory: Path, n: int) -> Path | None:
    """The PNG of picture version `n` of `images/<scene>/`: `v<n>.png`, else the still its sidecar names; None
    when neither exists."""
    png = directory / f"v{n}.png"
    if png.is_file():
        return png
    data = read_json(directory / f"v{n}.json")
    return still_image(project, data) if isinstance(data, dict) else None


def scene_ids(project: Path) -> list[str]:
    return [s["id"] for s in scenes_of(read_storyboard(project))]


def refuse_markdown(project: Path) -> None:
    """400 for a project holding storyboard.md, which Studio does not edit."""
    if os.path.lexists(project / STORYBOARD_MD):
        raise HttpError(400, f"{project} holds {STORYBOARD_MD}, which Studio does not edit; only a message is "
                             "accepted")


def scene_named(project: Path, body: dict) -> str:
    """`body["scene"]`, which must be the id of a scene in storyboard.json; 400 otherwise."""
    scene = body.get("scene")
    if not isinstance(scene, str) or scene not in scene_ids(project):
        raise HttpError(400, f"scene must be the id of a scene in {project / STORYBOARD}")
    return scene


def scene_images(project: Path, body: dict) -> Path:
    """`images/<scene>/` of the scene `body["scene"]`, which must be a directory that is not a symbolic link; 400
    otherwise."""
    d = project / "images" / scene_named(project, body)
    if (project / "images").is_symlink() or d.is_symlink() or not d.is_dir():
        raise HttpError(400, f"{d} is not a directory of the project")
    return d


def next_picture(directory: Path) -> int:
    """One more than the highest N among the directory's `v<N>.png` and `v<N>.json`, 1 when none."""
    try:
        names = os.listdir(directory)
    except OSError:
        return 1
    return max((int(m.group(1)) for f in names if (m := PICTURE_FILE.match(f))), default=0) + 1


# Film settings

def film_of(meta: object) -> dict:
    """`film` of project.json over the defaults, so every key is present. A voice of the earlier form has `backend`
    in place of `model`: its backend becomes the model id of `backend_model` (null when the config has none), and
    its name, speed and style are kept; any other voice without `model` is the default voice."""
    film = meta.get("film") if isinstance(meta, dict) else None
    out = {**default_film(), **(film if isinstance(film, dict) else {})}
    v = out["voice"]
    if isinstance(v, dict) and "model" not in v and OLD_VOICE_KEY in v:
        out["voice"] = {**default_film()["voice"], **{k: v[k] for k in ("name", "speed", "style") if k in v},
                        "model": backend_model(v[OLD_VOICE_KEY])}
    elif not isinstance(v, dict) or "model" not in v:
        out["voice"] = default_film()["voice"]
    return out


def _fail(message: str) -> HttpError:
    return HttpError(400, message)


def check_voice(v: object, what: str = "voice") -> dict:
    """A voice `{"model", "name", "speed", "style"}` as film.voice takes it (a null `model` is the `speech` model
    of config.yaml); 400 otherwise."""
    if not isinstance(v, dict) or set(v) != set(VOICE_KEYS):
        raise _fail(f"{what} must be an object with exactly {', '.join(VOICE_KEYS)}")
    if v["model"] is not None and not (isinstance(v["model"], str) and ":" in v["model"].strip(":")):
        raise _fail(f"{what}.model must be a speech model id <provider>:<model> or null")
    for k in ("name", "style"):
        if v[k] is not None and not (isinstance(v[k], str) and v[k].strip()):
            raise _fail(f"{what}.{k} must be a non-empty string or null")
    if not _number(v["speed"]) or not SPEED[0] <= v["speed"] <= SPEED[1]:
        raise _fail(f"{what}.speed must be a number from {SPEED[0]} to {SPEED[1]}")
    return v


def _check_music(v: object) -> None:
    keys = ("mode", "brief", "volume", "version")
    if not isinstance(v, dict) or set(v) != set(keys):
        raise _fail(f"music must be an object with exactly {', '.join(keys)}")
    if v["mode"] not in MUSIC_MODES:
        raise _fail(f"music.mode must be one of {', '.join(MUSIC_MODES)}")
    if not isinstance(v["brief"], str):
        raise _fail("music.brief must be a string")
    if v["volume"] not in VOLUMES:
        raise _fail(f"music.volume must be one of {', '.join(VOLUMES)}")
    n = v["version"]
    if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 1):
        raise _fail("music.version must be a positive integer or null")


def check_film_keys(film: object, whole: bool) -> dict:
    """The film settings `film` checked key by key against Film settings; with `whole`, every key is required."""
    if not isinstance(film, dict):
        raise _fail("film must be an object")
    unknown = [k for k in film if k not in FILM_KEYS]
    if unknown:
        raise _fail(f"unknown film key {unknown[0]!r}; allowed: {', '.join(FILM_KEYS)}")
    if whole and set(film) != set(FILM_KEYS):
        raise _fail(f"film must have every key: {', '.join(FILM_KEYS)}")
    if not film:
        raise _fail("film must set at least one key")
    if "voice" in film:
        check_voice(film["voice"], "voice")
    if "music" in film:
        _check_music(film["music"])
    if "shape" in film and film["shape"] not in SHAPES:
        raise _fail(f"shape must be one of {', '.join(SHAPES)}")
    if "length" in film and (type(film["length"]) is not int or film["length"] not in LENGTHS):
        raise _fail(f"length must be one of {', '.join(map(str, LENGTHS))}")
    if "author" in film and (not isinstance(film["author"], list)
                             or not all(isinstance(a, str) and a.strip() for a in film["author"])):
        raise _fail("author must be a list of non-empty names")
    if "brand" in film and film["brand"] is not None and not (isinstance(film["brand"], str)
                                                               and film["brand"].strip()):
        raise _fail("brand must be a non-empty string or null")
    if "review" in film and not isinstance(film["review"], bool):
        raise _fail("review must be true or false")
    if "silent" in film and not isinstance(film["silent"], bool):
        raise _fail("silent must be true or false")
    return film


def check_film(project: Path | None, current: dict, film: object, whole: bool) -> dict:
    """The whole film settings after applying `film` (checked with check_film_keys) to `current`; refuses a change of
    `shape` once storyboard.json has a scene, and a `music.version` that is not a complete music version made for
    the `music` object's mode. `project` None: a new project, with neither."""
    film = check_film_keys(film, whole)
    merged = {**current, **copy.deepcopy(film)}
    if project is None:
        if merged["music"]["version"] is not None:
            raise _fail("a new project has no music version")
        return merged
    if "shape" in film and film["shape"] != current.get("shape") and scene_ids(project):
        raise _fail("the shape cannot change once the storyboard has a scene; a phone version is a new project")
    n = merged["music"]["version"]
    if "music" in film and n is not None:
        mode = merged["music"]["mode"]
        if n not in [m["n"] for m in music_of(project) if m["source"] == mode]:
            raise _fail(f"music version {n} is not a complete music version with source {mode!r}")
    return merged


# Versions written by media:short-video

def _version_dirs(parent: Path) -> list[tuple[int, Path]]:
    """`(N, path)` of the `v<N>` directories of `parent` (links not followed), newest first."""
    try:
        with os.scandir(parent) as it:
            found = [(int(m.group(1)), Path(e.path)) for e in it
                     if (m := VERSION_DIR.match(e.name)) and e.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    return sorted(found, reverse=True)


def _complete(parent: Path, meta_name: str = META) -> list[tuple[int, Path, dict]]:
    """`(N, path, metadata)` of the complete versions of `parent`, newest first: those whose metadata file is a JSON
    object."""
    out = []
    for n, d in _version_dirs(parent):
        meta = read_json(d / meta_name)
        if isinstance(meta, dict):
            out.append((n, d, meta))
    return out


def _studio_json(d: Path) -> dict:
    data = read_json(d / STUDIO_JSON)
    return data if isinstance(data, dict) else {}


def _version_n(value: object) -> int | None:
    m = VERSION_DIR.match(value) if isinstance(value, str) else None
    return int(m.group(1)) if m else None


def _subdir(project: Path, *parts: str) -> Path | None:
    """`project/<parts>` when every part is a directory that is not a symbolic link; else None."""
    d = project
    for part in parts:
        d = d / part
        if d.is_symlink() or not d.is_dir():
            return None
    return d


def recording_of(project: Path, scene: str) -> dict | None:
    d = _subdir(project, "voice", scene)
    versions = _complete(d) if d else []
    if not versions:
        return None
    n, v, meta = versions[0]
    return {"n": n, "path": str(v / "narration.wav"), "duration": meta.get("duration"), "voice": meta.get("voice"),
            "created": meta.get("created_at")}


def scene_url(project: Path, page: Path) -> str:
    """The `/scene/<token>/` URL of a file of a version directory of a short-video project."""
    rel = page.relative_to(project.parent.parent)
    return SCENE_PREFIX + "/".join(quote(part) for part in rel.parts)


def page_of(project: Path, version: Path) -> tuple[Path | None, dict | None]:
    """The page a scene render was made from and the render's world.json: its own `index.html`, or for a cut of a
    world render `worlds/<world>/v<K>/index.html`; (None, world) when the page is not there."""
    own = version / "index.html"
    if own.is_file() and not own.is_symlink():
        return own, None
    world = read_json(version / WORLD_JSON)
    if not isinstance(world, dict):
        return None, None
    name, k = world.get("world"), world.get("version")
    k = _version_n(k) if isinstance(k, str) else k
    if not (isinstance(name, str) and SCENE_ID.match(name) and isinstance(k, int) and not isinstance(k, bool)):
        return None, world
    d = _subdir(project, "worlds", name, f"v{k}")
    page = d / "index.html" if d else None
    return (page if page and page.is_file() and not page.is_symlink() else None), world


def clip_of(project: Path, scene: str) -> dict | None:
    """The newest complete render of a scene. `page` and `page_url`: the HTML page it was rendered from (null for
    a scene of another engine), `start` the scene's start in that page (0, or its start in its world), `world` the
    world's name or null, `narration` the recording it was rendered with or null."""
    d = _subdir(project, "scenes", scene)
    versions = _complete(d) if d else []
    if not versions:
        return None
    n, v, meta = versions[0]
    page, world = page_of(project, v)
    start = world.get("start") if world else 0
    voice = meta.get("voice_version")
    wav = project / "voice" / scene / voice / "narration.wav" if isinstance(voice, str) and VERSION_DIR.match(voice) \
        else None
    return {"n": n, "path": str(v / "scene.mp4"), "contact": str(v / "contact.png"),
            "duration": meta.get("duration"), "created": meta.get("rendered_at"),
            "page": str(page) if page else None, "page_url": scene_url(project, page) if page else None,
            "start": start if _number(start) else 0, "world": world.get("world") if world else None,
            "narration": str(wav) if wav is not None and wav.is_file() else None}


def _root_duration(page: Path) -> float | None:
    """`data-duration` of the page's root element (the one with `data-composition-id`), or None."""
    try:
        html = page.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tag = ROOT_TAG.search(html)
    m = DATA_DURATION.search(tag.group(0)) if tag else None
    return float(m.group(1)) if m else None


def _page_file(d: Path) -> Path | None:
    page = d / "index.html"
    return page if page.is_file() and not page.is_symlink() else None


def _narration(project: Path, scene: str, voice: object) -> str | None:
    """The narration.wav of voice version `voice` (`v<N>`) of `scene`, or None."""
    if not (isinstance(voice, str) and VERSION_DIR.match(voice)):
        return None
    wav = project / "voice" / scene / voice / "narration.wav"
    return str(wav) if wav.is_file() else None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() if path.is_file() and not path.is_symlink() else None
    except OSError:
        return None


def _file_time(path: Path) -> str:
    """The modification time of `path`, ISO 8601 in local time."""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def page_scene(project: Path, scene: dict) -> dict | None:
    """The latest page of an HTML scene, rendered or not, as the scene player plays it; None for a scene of another
    engine or one with no page yet. A plain scene plays the latest `scenes/<id>/v<N>/` holding `index.html`; a world
    scene the latest `worlds/<world>/v<K>/` holding `index.html` and a world.json that names the scene. `n` is that
    version, `created` its index.html's time, `start` the scene's start in the page, `duration` its length
    (meta.json of a render of the version, else the root's `data-duration`, else timing.json; for a world scene
    world.json), `narration` the recording the page is timed to, and `video` the scene.mp4 rendered from this page
    version, or null."""
    sid = scene["id"]
    if scene.get("engine", "html") != "html":
        return None
    world = scene.get("world")
    if isinstance(world, str) and SCENE_ID.match(world):
        d = _subdir(project, "worlds", world)
        for k, v in _version_dirs(d) if d else []:
            page = _page_file(v)
            if page is None:
                continue
            plan = read_json(v / WORLD_JSON)
            spans = plan.get("scenes") if isinstance(plan, dict) else None
            span = next((s for s in spans if isinstance(s, dict) and s.get("id") == sid), None) \
                if isinstance(spans, list) else None
            if span is None or not _number(span.get("start")) or not _number(span.get("duration")):
                return None
            return {"n": k, "page": str(page), "page_url": scene_url(project, page), "created": _file_time(page),
                    "start": span["start"],
                    "duration": span["duration"], "world": world,
                    "narration": _narration(project, sid, span.get("voice_version")),
                    "video": _world_video(project, sid, world, v.name)}
        return None
    d = _subdir(project, "scenes", sid)
    for n, v in _version_dirs(d) if d else []:
        page = _page_file(v)
        if page is None:
            continue
        meta = read_json(v / META)
        meta = meta if isinstance(meta, dict) else None
        timing = read_json(v / "timing.json")
        duration = meta.get("duration") if meta else None
        if not _number(duration):
            duration = _root_duration(page)
        if duration is None and isinstance(timing, dict) and _number(timing.get("duration")):
            duration = timing["duration"]
        mp4 = v / "scene.mp4"
        return {"n": n, "page": str(page), "page_url": scene_url(project, page), "created": _file_time(page),
                "start": 0, "duration": duration,
                "world": None, "narration": _narration(project, sid, _read_text(v / "voice_version")),
                "video": str(mp4) if meta and mp4.is_file() else None}
    return None


def page_of_scene(project: Path, scene_id: str) -> dict | None:
    """`page_scene` of the storyboard's scene `scene_id`; None when the storyboard has no such scene."""
    scene = next((s for s in scenes_of(read_storyboard(project)) if s["id"] == scene_id), None)
    return page_scene(project, scene) if scene else None


def _world_video(project: Path, scene: str, world: str, version: str) -> str | None:
    """The scene.mp4 of the newest complete render of `scene` cut from world version `version`, or None."""
    d = _subdir(project, "scenes", scene)
    for _, v, meta in _complete(d) if d else []:
        if meta.get("world") == world and meta.get("world_version") == version and (v / "scene.mp4").is_file():
            return str(v / "scene.mp4")
    return None


def html_films_of(project: Path) -> list[dict]:
    """The HTML films (`film/html/v<N>/film.html` with its manifest.json), newest first. `scenes`: per scene of the
    manifest's segments in order, `{"id", "source"}` with the segment's `source` (the page version directory, or the
    scene.mp4, relative to the project; null for a card); `changes` and `created` from the version's studio.json
    (`created` the file's time without one)."""
    d = _subdir(project, "film", "html")
    out = []
    for n, v, manifest in _complete(d, MANIFEST) if d else []:
        path = v / FILM_HTML
        if not path.is_file() or path.is_symlink():
            continue
        segments = manifest.get("segments")
        segments = [s for s in segments if isinstance(s, dict)] if isinstance(segments, list) else []
        ends = [s["start"] + s["duration"] for s in segments if _number(s.get("start")) and _number(s.get("duration"))]
        scenes = [{"id": sid, "source": s.get("source") if isinstance(s.get("source"), str) else None}
                  for s in segments if isinstance(s.get("scenes"), list) for sid in s["scenes"] if isinstance(sid, str)]
        studio = _studio_json(v)
        created = studio.get("created") if isinstance(studio.get("created"), str) else _file_time(path)
        out.append({"n": n, "path": str(path), "duration": max(ends) if ends else None, "created": created,
                    "scenes": scenes, "changes": studio.get("changes")})
    return out


def is_html_film(project: Path, path: Path) -> bool:
    """`path` is the film.html of an HTML film version of the short-video project `project`."""
    return path.name == FILM_HTML and VERSION_DIR.match(path.parent.name) is not None \
        and path.parent.parent == project / "film" / "html"


def music_of(project: Path) -> list[dict]:
    """The complete music versions, newest first; `source` (`made`, `own`) and the last four keys from studio.json."""
    d = _subdir(project, "music")
    out = []
    for n, v, meta in _complete(d) if d else []:
        studio = _studio_json(v)
        name = meta.get("file")
        out.append({"n": n, "path": str(v / name) if isinstance(name, str) and name else None,
                    "source": studio.get("source"), "brief": studio.get("brief"), "note": studio.get("note"),
                    "duration": studio.get("duration"), "created": studio.get("created")})
    return out


def music_used(film: dict, music: list[dict]) -> int | None:
    """The music version a film would use: null for mode `none`; else, among the versions made for the mode,
    `film.music.version` when it is one of them, else the newest, else null."""
    mode = film["music"]["mode"]
    if mode == "none":
        return None
    numbers = [m["n"] for m in music if m["source"] == mode]
    pick = film["music"]["version"]
    return pick if pick in numbers else (numbers[0] if numbers else None)


def review_of(film_dir: Path) -> dict | None:
    """A film version's review.json, the film critic's findings that hold; None without it or when it is not a JSON
    object."""
    data = read_json(film_dir / REVIEW_JSON)
    return data if isinstance(data, dict) else None


def caption_changed(film_scenes: object, storyboard: object) -> list[str]:
    """The ids of the storyboard's scenes whose `show_author` differs from the one the MP4 was assembled with (the
    `show_author` of its manifest's scene entry). An entry without one (an MP4 made before the key existed), and a
    scene the MP4 does not have, count as unchanged here."""
    used = {e["id"]: e["show_author"] for e in film_scenes if isinstance(e, dict) and isinstance(e.get("show_author"), bool)
            and isinstance(e.get("id"), str)} if isinstance(film_scenes, list) else {}
    return [s["id"] for s in scenes_of(storyboard) if s["id"] in used and used[s["id"]] != show_author(s)]


def films_of(project: Path, storyboard: object = None) -> list[dict]:
    """The complete film versions, newest first; with the `storyboard`, each with `caption_changed`."""
    d = _subdir(project, "film")
    out = []
    for n, v, manifest in _complete(d, MANIFEST) if d else []:
        music = manifest.get("music")
        out.append({"n": n, "path": str(v / "film.mp4"), "duration": manifest.get("duration"),
                    "created": manifest.get("created_at"), "scenes": manifest.get("scenes"),
                    "music": _version_n(music.get("version")) if isinstance(music, dict) else None,
                    "changes": _studio_json(v).get("changes"), "review": review_of(v),
                    "caption_changed": caption_changed(manifest.get("scenes"), storyboard)})
    return out


def film_count(project: Path) -> int:
    d = _subdir(project, "film")
    return len(_complete(d, MANIFEST)) if d else 0


def samples_of(project: Path) -> list[dict]:
    """The voice samples, newest first: a `voice-<k>/narration.wav` with its sidecar `voice-<k>.json`, a JSON
    object."""
    d = _subdir(project, "samples")
    out = []
    try:
        names = os.listdir(d) if d else []
    except OSError:
        names = []
    for f in names:
        m = SAMPLE_JSON.match(f)
        wav = d / f"voice-{m.group(1)}" / SAMPLE_WAV if m else None
        if wav is None or wav.parent.is_symlink() or not wav.is_file():
            continue
        data = read_json(d / f)
        if isinstance(data, dict):
            out.append({"k": int(m.group(1)), "path": str(wav), "voice": data.get("voice"), "text": data.get("text")})
    return sorted(out, key=lambda s: s["k"], reverse=True)


# Scene state

STATES = ("ready", "voice", "render")


def scene_state(scene: dict, storyboard: dict, status: object, film: dict) -> str:
    """The state shown for `scene`: its entry in status.json, moved to `voice` when the narration, speakers or
    voice changed since that entry and to `render` when another key of the scene (except `FILM_ONLY_KEYS`), or a
    template scene's author or brand, changed; a scene without an entry needs a recording when it has narration, else
    a render."""
    narrated = bool(scene.get("narration"))
    entries = status.get("scenes") if isinstance(status, dict) else None
    entry = entries.get(scene["id"]) if isinstance(entries, dict) else None
    if not isinstance(entry, dict) or entry.get("state") not in STATES or not isinstance(entry.get("basis"), dict):
        return "voice" if narrated else "render"
    recorded, basis = entry["state"], normalize(entry["basis"])
    ran = status.get("film") if isinstance(status.get("film"), dict) else {}
    now = normalize(scene)
    for k in FILM_ONLY_KEYS:
        now.pop(k, None)
        basis.pop(k, None)
    if narrated and (normalize(film.get("voice")) != normalize(ran.get("voice"))
                     or normalize(storyboard.get("speakers")) != normalize(status.get("speakers"))):
        return "voice"
    if any((k in now) != (k in basis) or now.get(k) != basis.get(k) for k in ("narration", "speakers", "voices")):
        return "voice"
    if now == basis and ("template" not in now or all(
            normalize(film.get(k)) == normalize(ran.get(k)) and (k in film) == (k in ran)
            for k in ("author", "brand"))):
        return recorded
    return "render" if recorded == "ready" else recorded


# /api/project

def video_details(project: Path, meta: object) -> dict:
    """`video` of a short-video project in /api/project."""
    storyboard = read_storyboard(project)
    out: dict = {"storyboard": storyboard, "storyboard_mtime": storyboard_mtime(project)}
    if os.path.lexists(project / STORYBOARD_MD):
        out["error"] = f"the project holds {STORYBOARD_MD}, which Studio does not edit"
    elif storyboard is None and out["storyboard_mtime"] is not None:
        out["error"] = f"{STORYBOARD} is not a JSON object"
    film = film_of(meta)
    status = read_json(project / STATUS)
    scenes = []
    for s in scenes_of(storyboard):
        sid = s["id"]
        d = _subdir(project, "images", sid)
        pictures = scene_pictures(project, d) if d else []
        image = s.get("image")
        m = re.fullmatch(rf"{sid}/v([1-9][0-9]*)\.png", image) if isinstance(image, str) else None
        picture = int(m.group(1)) if m and int(m.group(1)) in [v["n"] for v in pictures] else None
        # A drawn scene shows its newest still where a scene with a picture shows the picture it uses.
        still = next((v["n"] for v in pictures if is_still(v)), None) if is_drawn(s) else None
        scenes.append({"id": sid, "state": scene_state(s, storyboard, status, film), "pictures": pictures,
                       "picture": picture, "still": still, "recording": recording_of(project, sid),
                       "clip": clip_of(project, sid), "page": page_scene(project, s), "show_author": show_author(s)})
    music = music_of(project)
    out |= {
        "scenes": scenes,
        "music": music,
        "music_used": music_used(film, music),
        "films": films_of(project, storyboard),
        "html_films": html_films_of(project),
        "samples": samples_of(project),
        "status": status.get("created") if isinstance(status, dict) else None,
    }
    return out


def sources_of(project: Path) -> list[str]:
    """Absolute paths of the files directly in sources/."""
    d = _subdir(project, "sources")
    if d is None:
        return []
    return sorted(str(f) for f in d.iterdir() if f.is_file() and not f.is_symlink() and not f.name.startswith("."))


# Requests

def writes_pictures(req: dict, project: str, scene: str) -> bool:
    """True when the request writes pictures of `scene` in `project`."""
    if req.get("project") != project:
        return False
    action = req.get("action")
    return action in FILM_PICTURE_ACTIONS or (action in SCENE_PICTURE_ACTIONS and req.get("scene") == scene)


# Watched paths

def _dirs(directory: Path) -> list[str]:
    """The subdirectories of `directory`, none when it is a symbolic link; links not followed."""
    if directory.is_symlink():
        return []
    try:
        with os.scandir(directory) as it:
            return sorted(e.name for e in it if e.is_dir(follow_symlinks=False))
    except OSError:
        return []


def watched_subdirs(project: Path) -> list[str]:
    """The subdirectories of a short-video project whose files are watched, relative to it."""
    out = ["sources", "samples", "images", "voice", "scenes", "worlds", "music", "film", os.path.join("film", "html")]
    out += [os.path.join("samples", s) for s in _dirs(project / "samples") if SAMPLE_DIR.match(s)]
    for scene in _dirs(project / "images"):
        out += [os.path.join("images", scene), os.path.join("images", scene, "marks")]
    for top in ("voice", "scenes"):
        for scene in _dirs(project / top):
            out.append(os.path.join(top, scene))
            out += [os.path.join(top, scene, v) for v in _dirs(project / top / scene) if VERSION_DIR.match(v)]
    for world in _dirs(project / "worlds"):
        out.append(os.path.join("worlds", world))
        out += [os.path.join("worlds", world, v) for v in _dirs(project / "worlds" / world) if VERSION_DIR.match(v)]
    for top in ("music", "film", os.path.join("film", "html")):
        out += [os.path.join(top, v) for v in _dirs(project / top) if VERSION_DIR.match(v)]
    return out
