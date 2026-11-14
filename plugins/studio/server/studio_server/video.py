"""Short videos: a project of kind `short-video` is a `media:short-video` project directory with Studio's project.json.

The storyboard is `storyboard.json` (the structure media:short-video parses `storyboard.md` into); the page edits it
through `/api/storyboard`, checked here by the same structural rules media:short-video applies when it reads it. The
agent writes `status.json` (each scene's state and the scene object it was computed on); the server compares the
storyboard with it to show each scene's state, and reads the version directories media:short-video writes
(`voice/<scene>/v<N>/`, `scenes/<scene>/v<N>/`, `music/v<N>/`, `film/v<N>/`) and the scene pictures in
`images/<scene>/`. Nothing here runs or imports media:short-video.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

from plugin_settings import get

from .deck import versions_of
from .paths import HttpError, read_json

DIRECTORY = "short-video"
STORYBOARD = "storyboard.json"
STORYBOARD_MD = "storyboard.md"
STATUS = "status.json"
META = "meta.json"
MANIFEST = "manifest.json"
STUDIO_JSON = "studio.json"
REVIEW_JSON = "review.json"
SCENE_ID = re.compile(r"^[a-z0-9_]+$")
VERSION_DIR = re.compile(r"^v([1-9][0-9]*)$")
SAMPLE_JSON = re.compile(r"^voice-([1-9][0-9]*)\.json$")
SAMPLE_WAV = "narration.wav"
SAMPLE_DIR = re.compile(r"^voice-[1-9][0-9]*$")
PICTURE_FILE = re.compile(r"^v([1-9][0-9]*)\.(?:png|json)$")

# The storyboard structure, as media:short-video's storyboard check has it.
TOP_KEYS = ("title", "topic", "source", "speakers", "scenes")
SCENE_KEYS = ("id", "template", "image", "brief", "engine", "preview", "narration", "beats", "speakers", "voices")
VOICE_KEYS = ("backend", "name", "speed", "style")
ENGINES = ("html", "manim", "video", "clip")
# The template names of media:short-video's default settings, which Studio's settings.yaml does not change.
TEMPLATES = ("title", "summary", "end")

# Film settings (`film` in project.json).
BACKENDS = ("kokoro", "speech", "chatterbox")
SPEED = (0.5, 2.0)
MUSIC_MODES = ("made", "own", "none")
VOLUMES = ("quiet", "normal", "louder")
SHAPES = ("16:9", "9:16")
LENGTHS = (30, 60, 120, 180)
FILM_KEYS = ("voice", "music", "shape", "length", "author", "brand", "review")
FILM_DEFAULTS = {
    "voice": {"backend": "kokoro", "name": None, "speed": 1.0, "style": None},
    "music": {"mode": "made", "brief": "", "volume": "normal", "version": None},
    "shape": "16:9",
    "length": 60,
    "author": [],
    "brand": None,
    "review": True,
}
PHONE_SHAPE = "9:16"
PHONE_LENGTH = 60

AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
SOURCE_SUFFIXES = (".pdf", ".txt", ".md", ".docx", ".pptx", ".xlsx", ".csv", ".html") + AUDIO_SUFFIXES

# Requests that write pictures of one scene (named in `scene`), and requests that write pictures of many scenes.
SCENE_PICTURE_ACTIONS = ("change", "variations", "other-styles")
FILM_PICTURE_ACTIONS = ("storyboard", "use-style", "style-samples", "add-scene")


def default_authors() -> list[str]:
    """The names of the `AUTHOR_NAME` setting (comma-separated), a new film's "Made by"; [] when it is not set."""
    return [n for n in (" ".join(x.split()) for x in (get("AUTHOR_NAME", "") or "").split(",")) if n]


def default_film() -> dict:
    """The settings of a new film: FILM_DEFAULTS with `author` from the AUTHOR_NAME setting."""
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
        if k not in VOICE_KEYS:
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
    return out


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
    for k in ("template", "image", "brief", "engine", "preview"):
        if k in s and not isinstance(s[k], str):
            err(f"{label}: `{k}` must be a string")
    engine, template = s.get("engine"), s.get("template")
    if engine is not None and engine not in ENGINES:
        err(f"{label}: `engine` must be one of {', '.join(ENGINES)}")
    if template is not None:
        if template not in TEMPLATES:
            err(f"{label}: `template` must be one of {', '.join(TEMPLATES)}")
        if engine is not None:
            err(f"{label}: a template scene takes no `engine`")
        if "brief" in s:
            err(f"{label}: a template scene takes no `brief`")
    elif engine != "clip" and not s.get("brief"):
        err(f"{label}: missing `brief`")
    if s.get("image") == "":
        err(f"{label}: `image` is empty; name a file under images/ or leave it out")
    silent = engine == "clip" and template is None
    narration = s.get("narration", [] if silent else None)
    if not isinstance(narration, list) or not all(_text(x) for x in narration):
        err(f"{label}: `narration` must be a list of non-empty sentences")
        return
    if not narration and not silent:
        err(f"{label}: missing sentences in `narration` (only a scene with `engine` clip may have none)")
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


def has_picture(scene: dict) -> bool:
    """Whether a scene has a picture: it names an `image`, or it is a template scene (its picture is the
    background)."""
    return bool(scene.get("image")) or bool(scene.get("template"))


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
    """`film` of project.json over the defaults, so every key is present."""
    film = meta.get("film") if isinstance(meta, dict) else None
    return {**default_film(), **(film if isinstance(film, dict) else {})}


def _fail(message: str) -> HttpError:
    return HttpError(400, message)


def check_voice(v: object, what: str = "voice") -> dict:
    """A voice `{"backend", "name", "speed", "style"}` as film.voice takes it; 400 otherwise."""
    if not isinstance(v, dict) or set(v) != set(VOICE_KEYS):
        raise _fail(f"{what} must be an object with exactly {', '.join(VOICE_KEYS)}")
    if v["backend"] not in BACKENDS:
        raise _fail(f"{what}.backend must be one of {', '.join(BACKENDS)}")
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


def clip_of(project: Path, scene: str) -> dict | None:
    d = _subdir(project, "scenes", scene)
    versions = _complete(d) if d else []
    if not versions:
        return None
    n, v, meta = versions[0]
    return {"n": n, "path": str(v / "scene.mp4"), "contact": str(v / "contact.png"),
            "duration": meta.get("duration"), "created": meta.get("rendered_at")}


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


def films_of(project: Path) -> list[dict]:
    """The complete film versions, newest first."""
    d = _subdir(project, "film")
    out = []
    for n, v, manifest in _complete(d, MANIFEST) if d else []:
        music = manifest.get("music")
        out.append({"n": n, "path": str(v / "film.mp4"), "duration": manifest.get("duration"),
                    "created": manifest.get("created_at"), "scenes": manifest.get("scenes"),
                    "music": _version_n(music.get("version")) if isinstance(music, dict) else None,
                    "changes": _studio_json(v).get("changes"), "review": review_of(v)})
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
    voice changed since that entry and to `render` when another key of the scene, or a template scene's author or
    brand, changed; a scene without an entry needs a recording when it has narration, else a render."""
    narrated = bool(scene.get("narration"))
    entries = status.get("scenes") if isinstance(status, dict) else None
    entry = entries.get(scene["id"]) if isinstance(entries, dict) else None
    if not isinstance(entry, dict) or entry.get("state") not in STATES or not isinstance(entry.get("basis"), dict):
        return "voice" if narrated else "render"
    recorded, basis = entry["state"], normalize(entry["basis"])
    ran = status.get("film") if isinstance(status.get("film"), dict) else {}
    now = normalize(scene)
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
        pictures = versions_of(d) if d else []
        image = s.get("image")
        m = re.fullmatch(rf"{sid}/v([1-9][0-9]*)\.png", image) if isinstance(image, str) else None
        picture = int(m.group(1)) if m and int(m.group(1)) in [v["n"] for v in pictures] else None
        scenes.append({"id": sid, "state": scene_state(s, storyboard, status, film), "pictures": pictures,
                       "picture": picture, "recording": recording_of(project, sid), "clip": clip_of(project, sid)})
    music = music_of(project)
    out |= {
        "scenes": scenes,
        "music": music,
        "music_used": music_used(film, music),
        "films": films_of(project),
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
    out = ["sources", "samples", "images", "voice", "scenes", "music", "film"]
    out += [os.path.join("samples", s) for s in _dirs(project / "samples") if SAMPLE_DIR.match(s)]
    for scene in _dirs(project / "images"):
        out += [os.path.join("images", scene), os.path.join("images", scene, "marks")]
    for top in ("voice", "scenes"):
        for scene in _dirs(project / top):
            out.append(os.path.join(top, scene))
            out += [os.path.join(top, scene, v) for v in _dirs(project / top / scene) if VERSION_DIR.match(v)]
    for top in ("music", "film"):
        out += [os.path.join(top, v) for v in _dirs(project / top) if VERSION_DIR.match(v)]
    return out
