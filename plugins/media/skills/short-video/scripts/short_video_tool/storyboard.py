"""Parse and validate the storyboard: `storyboard.md` or `storyboard.json`.

A project has one of the two files (`source_file`; both is an error).
`storyboard.json` stores the parsed dict described below as JSON;
`parse_markdown` and `parse_json` both end in `check`, which holds every
structural rule, so the two files obey the same rules.

`storyboard.md` is the file people edit:

    # <title>

    Topic: <one paragraph>
    Source: sources/notes.md

    ## <scene id>
    Image: a.png
    Brief: <animation idea>

    | Narration | On screen |
    |---|---|
    | <sentence> | <what the viewer sees; the word an event lands on in quotes> |

    ## title
    Template: title

    | Narration | On screen |
    |---|---|
    | <sentence> | <text shown: the title in row 1, a line under it in rows 2-3> |

The header may define speakers, other voices than the default one (`voice:`
in settings), in one table before the first scene:

    | Speaker | Model | Voice | Speed | Style |
    |---|---|---|---|---|
    | guest | vertex:gemini-3.8-flash-tts | Kore | 1.0 | warm, curious |

A scene table may then start with a Speaker column,
`| Speaker | Narration | On screen |`, whose cells name a speaker of that
table; an empty cell is the default voice. After On screen it may have any of
the columns Model, Voice, Speed, Style, in any order: a sentence's own voice
settings over its speaker's voice; an empty cell is unset.

`<!-- ... -->` comments (lines starting with `<!--` up to the line holding
`-->`) are ignored. `Source` is optional. Author, voice and music are set in
the project's `settings.yaml`, not here. A scene with
`Template: <name>` (names and rules under `templates:` in the settings: title,
summary, end) starts from the suggested page `assets/<name>.html`: it takes no
`Brief:`, its `Image:` is optional, and its On screen cells are the text
shown. A field's value continues on the
following lines up to a blank line. A literal `|` in a cell is written `\\|`.
All whitespace inside a value is collapsed to single spaces, so reflowing the
file changes nothing downstream.

The parsed dict has the shape the rest of the code uses. Top level: `title`,
`topic`, optional `source` (path under `sources/`), `speakers` when the
header has a speakers table (name to `model`, `name`, `speed`, `style`,
an empty cell as None) and `scenes`. Each scene:
`id` (`[a-z0-9_]+`, unique), `image` (path under `images/`, only when
given), `brief`,
`narration` (list of sentences) and `beats` (same length as `narration`). A
scene whose table has the Speaker column also has `speakers`, the Speaker
cell of each sentence (None when empty); one with voice columns has `voices`,
per sentence None or a dict of the set fields among `model`, `name`,
`speed`, `style`; one with an image preview line has `preview`, its path. A
template scene has `template` instead of `brief` and `image` only when given.
The author is not part of the dict (`read`, storyboard.json): `load` adds a
copy of the film's author (from settings), when one is set, to each template
scene for its `card.js`.

A scene may name its engine (`engine.Engine`) with `Engine: html` (the
default, HyperFrames), `Engine: manim` (a Manim Community Edition `scene.py`,
see `manim_scene`) or `Engine: video` (a video model animates the scene's
image from a prompt, see `video_scene`). An HTML or manim scene needs `Brief:`
and its `Image:` is optional: an HTML scene without one draws everything on
screen in its page. A video scene needs both: `Image:` is the still the model
animates, `Brief:` the motion. A manim or video scene cannot be a template
scene. `Engine: presenter` (a presenter model makes the person in the scene's
`Image:` speak the scene's narration recording, see `presenter_scene`) needs
`Image:`; its `Brief:` is optional and, when given, replaces the model's own
prompt; it cannot be a template scene. The parsed scene has `engine` only when
`Engine:` is given. A video
scene may have `Ambience: off` (or `on`, the default): the parsed `ambience`
is False (True), and with False the model clip's sound track is not mixed
under the narration (`video_scene.render`). No other scene takes it.

`Engine: clip` marks a scene whose video is a clip made outside short-video and
imported with `clip` (see `clip`). Its `Brief:` and
`Image:` are optional (the parsed scene has `brief` and `image` only when
given), and it cannot be a template scene. A clip scene may have no
table: its `narration` and `beats` are then empty, and the scene is silent
and lasts its clip.

An HTML scene without a table has `Length: <seconds>` (parsed `length`, a
number above 0): it is silent and lasts that long. Only such a scene takes
`Length:`; it cannot be a template scene.

`World: <name>` (`[a-z0-9_]+`, parsed `world`) puts an HTML scene in a shared
world: the consecutive scenes with the same name are cut from one page (see
`world`). A world scene takes no `Template:` and no `Image:`.

Any scene may have `Show author: false` (or `true`; the value is case
insensitive, anything else is an error): the parsed `show_author` is False
(True), and with False the film's creator caption ("Created by <author>") is
not drawn over the scene. The parsed scene has `show_author` only when the key
is given; without it the scene follows its template's `show_author` rule
(`templates:` in the settings), and a scene without either is captioned
(`show_author`). In storyboard.json `show_author` is true or false; null is an
error (leave the key out instead). Set False on a scene whose picture already
shows the author's name, so the name is not burned in twice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import brand, settings, state
from .engine import Engine

MD_FILE = "storyboard.md"
JSON_FILE = "storyboard.json"
SCENE_ID_RE = re.compile(r"^[a-z0-9_]+$")

HEADER_KEYS = ("Topic", "Source")
# Header keys of older storyboards and where their values live now.
MOVED_KEYS = {"Voice": "voice", "Music": "music", "Author": "author"}
SCENE_KEYS = ("Image", "Brief", "Template", "Engine", "Ambience", "Length", "World", "Show author")
# Every key of storyboard.md by its lowercase form: a key is matched in any case.
KNOWN_KEYS = {k.lower(): k for k in HEADER_KEYS + tuple(MOVED_KEYS) + SCENE_KEYS}
# A template rule of an earlier version, and its replacement with the inverted meaning.
OLD_TEMPLATE_KEY = "shows_author"
# `Ambience:` values of storyboard.md and the parsed `ambience`.
AMBIENCE_VALUES = {"on": True, "off": False}
# `Show author:` values of storyboard.md and the parsed `show_author`.
SHOW_AUTHOR_VALUES = {"true": True, "false": False}
# Values of a scene's `Engine:` key; a scene without one uses the first.
ENGINES = tuple(e.value for e in Engine)
CLIP = Engine.CLIP
VIDEO = Engine.VIDEO
PRESENTER = Engine.PRESENTER
HTML = Engine.HTML
# Engines whose scene needs no `Brief:`.
NO_BRIEF = (CLIP, PRESENTER)
TABLE_HEADER = ["narration", "on screen"]
# The fields of a voice: a speaker's, or a sentence's own settings.
VOICE_KEYS = ("model", "name", "speed", "style")
# Optional scene table columns after On screen: header name to voice field.
VOICE_COLUMNS = {"model": "model", "voice": "name", "speed": "speed", "style": "style"}
COLUMN_TITLES = {"speaker": "Speaker", "narration": "Narration", "on screen": "On screen",
                 "model": "Model", "voice": "Voice", "speed": "Speed", "style": "Style"}
# The header's speakers table.
SPEAKERS_HEADER = ["speaker", "model", "voice", "speed", "style"]
# The voice field and column of an earlier version, and how each of its values maps to a model.
OLD_VOICE_KEY = "backend"
# The earlier backend that meant config.yaml's `speech` model; every other earlier backend is a provider kind.
SPEECH_BACKEND = "speech"


def backend_model(backend: str) -> str | None:
    """The model id an earlier voice `backend` maps to: None (config.yaml's `speech` model) for `speech`, else the
    configured speech model of the provider kind of that name (`ai_models.speech.model_of_kind`), None when the
    config has none."""
    from ai_models import AIModelsError, speech

    if backend == SPEECH_BACKEND:
        return None
    try:
        return speech.model_of_kind(backend)
    except AIModelsError:
        return None


def backend_moved(backend: str | None = None) -> str:
    """The message for an earlier `backend` field or Backend column; with the `backend` value, its model id in this
    config.yaml when it has one."""
    msg = ("Backend (`backend`) became Model (`model`), a speech model id <provider>:<model> of config.yaml: for an "
           "earlier backend named after a provider kind (kokoro, chatterbox), a model of a provider of that kind (the "
           "voiceover skill's `routes` lists the speech models); for speech, an empty Model (config.yaml's "
           "tasks.speech)")
    if backend and backend != SPEECH_BACKEND and (model := backend_model(backend)):
        msg += f"; here {backend} is {model}"
    return msg


# Keys of the storyboard structure (storyboard.json) and of each scene.
TOP_KEYS = ("title", "topic", "source", "speakers", "scenes")
SCENE_FIELDS = ("id", "template", "image", "brief", "engine", "ambience", "length", "world", "show_author", "preview",
                "narration", "beats", "speakers", "voices")
# A heading is `#`s followed by a space (or nothing): `#0f1420` in a Brief is text.
HEADING_RE = re.compile(r"^#+(\s|$)")
# A key is a word starting with a capital letter, or two words when they are a key of two words (`Show author:`).
# A known key matches in any case (`ENGINE:`, `Show Author:`).
KEY_RE = re.compile(r"^([A-Z][A-Za-z]*(?: [A-Za-z]+)?):(?:\s+(.*))?$")
UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
# An image preview line in a scene: HTML <img> (optionally inside <a href>),
# or Markdown ![](...) (optionally inside a link).
PREVIEW_RES = (
    re.compile(r'^(?:<a\s[^>]*>\s*)?<img\s[^>]*\bsrc="([^"]+)"[^>]*>(?:\s*</a>)?$', re.I),
    re.compile(r"^\[!\[[^\]]*\]\(<?([^)>]+?)>?\)\]\([^)]*\)$"),
    re.compile(r"^!\[[^\]]*\]\(<?([^)>]+?)>?(?:\s+\"[^\"]*\")?\)$"),
)


def _templates() -> dict:
    """Template scenes and their rules (position, max_rows, show_author, hold_seconds)."""
    return settings.get()["templates"]


def preview_src(line: str) -> str | None:
    """The image path of a preview line, or None if the line is not one."""
    for r in PREVIEW_RES:
        m = r.match(line)
        if m:
            return m.group(1).strip()
    return None


def preview_line(image: str) -> str:
    """The preview line, written below `Brief:` and above the table (path
    relative to storyboard.md)."""
    rel = image if image.startswith("images/") else f"images/{image}"
    return _preview_html(rel)


def _preview_html(src: str) -> str:
    """A small image that links to the full-size file."""
    return f'<a href="{src}"><img src="{src}" width="{settings.get()['storyboard']['preview_width']}"></a>'


class StoryboardError(Exception):
    """The storyboard file cannot be read or parsed."""


@dataclass
class Validation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize(obj):
    """Collapse runs of whitespace in every string and strip it, recursively."""
    if isinstance(obj, str):
        return " ".join(obj.split())
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


# --- The storyboard structure: one check for both files ---------------------


# How a field is named in the messages of each file.
JSON_NAMES = {"scenes": "an entry to `scenes`", "no_speaker": "use null for the default voice",
              "narration": "sentences in `narration`", "clip_scene": "a scene with `engine` clip",
              "video_scene": "a scene with `engine` video", "presenter_scene": "a scene with `engine` presenter",
              "ambience": "`ambience`",
              "ambience_values": "true or false", "length": "`length`", "world": "`world`",
              "silent_scene": "a scene with `engine` clip or with `length`", "show_author": "`show_author`",
              "show_author_values": "true or false"}
MD_NAMES = {
    "title": "`# <title>`", "topic": "`Topic:` paragraph", "source": "`Source:`",
    "scenes": "a `## <scene id>` section", "image": "`Image:`", "brief": "`Brief:`",
    "template": "`Template:`", "engine": "`Engine:`", "narration": "the `| Narration | On screen |` table",
    "beats": "On screen", "speakers": "the speakers table in the header (`| Speaker | Model | Voice | Speed | "
    "Style |`)", "no_speaker": "leave the cell empty for the default voice",
    "clip_scene": "an `Engine: clip` scene", "video_scene": "an `Engine: video` scene",
    "presenter_scene": "an `Engine: presenter` scene",
    "ambience": "`Ambience:`", "ambience_values": "on or off", "length": "`Length:`", "world": "`World:`",
    "silent_scene": "an `Engine: clip` scene or a scene with `Length:`",
    "show_author": "`Show author:`", "show_author_values": "true or false",
}


def _text(v) -> bool:
    return isinstance(v, str) and bool(v)


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _voice_fields(v, path: tuple, label: str, err) -> None:
    """Types of one voice object (`model`, `name`, `speed`, `style`, each optional)."""
    if not isinstance(v, dict):
        err(path, f"{label}: must be an object with any of {', '.join(VOICE_KEYS)}")
        return
    for k, x in v.items():
        if k == OLD_VOICE_KEY:
            err(path + (k,), f"{label}: {backend_moved(x if isinstance(x, str) else None)}")
        elif k not in VOICE_KEYS:
            err(path + (k,), f"{label}: unknown key `{k}`; allowed: {', '.join(VOICE_KEYS)}")
        elif x is not None and not (_number(x) if k == "speed" else isinstance(x, str)):
            err(path + (k,), f"{label}: `{k}` must be {'a number' if k == 'speed' else 'a string'} or null")


def check(data, names: dict | None = None) -> list[tuple[tuple, str]]:
    """Every structural problem of a storyboard dict, as `(path, message)`.

    `path` locates the problem in the structure (`("scenes", 2, "voices", 0,
    "speed")`); `names` maps a field to how the file names it (default: the
    JSON key). Checked: the keys and their types, required keys per scene kind,
    engines, templates, speaker names, and that `beats`, `speakers` and
    `voices` are as long as `narration`."""
    names = names or JSON_NAMES
    out: list[tuple[tuple, str]] = []

    def err(path: tuple, msg: str) -> None:
        out.append((path, msg))

    def name(key: str) -> str:
        return names.get(key, f"`{key}`")

    if not isinstance(data, dict):
        return [((), "the storyboard must be an object")]
    for k in data:
        if k not in TOP_KEYS:
            err((k,), f"unknown key `{k}`; " + (f"it is set in the project's settings.yaml (`{k}:`)"
                                                 if k in MOVED_KEYS.values() else f"allowed: {', '.join(TOP_KEYS)}"))
    for k in ("title", "topic"):
        if k in data and not isinstance(data[k], str):
            err((k,), f"`{k}` must be a string")
        elif not data.get(k):
            err((k,), f"missing {name(k)}")
    if "source" in data and not _text(data["source"]):
        err(("source",), f"{name('source')} must be a path under sources/")
    speakers = data.get("speakers", {})
    if not isinstance(speakers, dict):
        err(("speakers",), "`speakers` must be an object of speaker name to voice")
        speakers = {}
    for sp, v in speakers.items():
        if not SCENE_ID_RE.match(sp):
            err(("speakers", sp), f"invalid speaker name {sp!r}: use lowercase letters, digits and _ only")
        _voice_fields(v, ("speakers", sp), f"speaker {sp!r}", err)
    scenes_ = data.get("scenes")
    if not isinstance(scenes_, list) or not scenes_:
        err(("scenes",), f"no scenes; add {name('scenes')}")
        scenes_ = scenes_ if isinstance(scenes_, list) else []
    seen: set[str] = set()
    templates = _templates()
    for i, s in enumerate(scenes_):
        _check_scene(s, ("scenes", i), seen, speakers, templates, name, err)
    _check_worlds(scenes_, name, err)
    return out


def _check_worlds(scenes_: list, name, err) -> None:
    """The scenes of one world are consecutive."""
    last: dict[str, int] = {}
    for i, s in enumerate(scenes_):
        w = s.get("world") if isinstance(s, dict) else None
        if not isinstance(w, str):
            continue
        if w in last and last[w] != i - 1:
            err(("scenes", i, "world"), f"scene {s.get('id')!r}: the scenes of world {w!r} must be consecutive; "
                                        f"move it next to the others or give it another {name('world')}")
        last[w] = i


def _check_scene(s, p: tuple, seen: set, speakers: dict, templates: dict, name, err) -> None:
    if not isinstance(s, dict):
        err(p, f"scene {p[1] + 1}: must be an object")
        return
    sid = s.get("id")
    if not isinstance(sid, str) or not SCENE_ID_RE.match(sid):
        err(p + ("id",), f"invalid scene id {sid!r}: use lowercase letters, digits and _ only")
        label = f"scene {p[1] + 1}"
    else:
        label = f"scene {sid!r}"
        if sid in seen:
            err(p + ("id",), f"duplicate scene id {sid!r}")
        seen.add(sid)
    for k in s:
        if k not in SCENE_FIELDS:
            err(p + (k,), f"{label}: unknown key `{k}`; allowed: {', '.join(SCENE_FIELDS)}")
    for k in ("template", "image", "brief", "engine", "preview"):
        if k in s and not isinstance(s[k], str):
            err(p + (k,), f"{label}: {name(k)} must be a string")
    engine, template = s.get("engine"), s.get("template")
    if engine is not None and engine not in ENGINES:
        err(p + ("engine",), f"{label}: {name('engine')} must be one of {', '.join(ENGINES)}")
    if template is not None:
        if template not in templates:
            err(p + ("template",), f"{label}: {name('template')} must be one of {', '.join(templates)}")
        if engine is not None:
            err(p + ("engine",), f"{label}: a template scene takes no {name('engine')}")
        if "brief" in s:
            err(p + ("brief",), f"{label}: a template scene takes no {name('brief')}")
    elif engine not in NO_BRIEF and not s.get("brief"):
        err(p + ("brief",), f"{label}: missing {name('brief')}")
    if s.get("image") == "":
        err(p + ("image",), f"{label}: {name('image')} is empty; name a file under images/ or leave it out")
    elif engine == VIDEO and template is None and "image" not in s:
        err(p + ("image",), f"{label}: missing {name('image')}; {name('video_scene')} animates that image")
    elif engine == PRESENTER and template is None and "image" not in s:
        err(p + ("image",), f"{label}: missing {name('image')}; {name('presenter_scene')} makes the person in that "
                            "image speak")
    if "world" in s:
        world = s["world"]
        if not isinstance(world, str) or not SCENE_ID_RE.match(world):
            err(p + ("world",), f"{label}: invalid {name('world')} {world!r}: use lowercase letters, digits and _ only")
        elif template is not None or "image" in s or (engine is not None and engine != HTML):
            err(p + ("world",), f"{label}: a world scene is an HTML scene without {name('template')} and without "
                                f"{name('image')}; it draws everything in the world's page")
    has_length = "length" in s
    if has_length:
        length = s["length"]
        if not _number(length) or length <= 0:
            err(p + ("length",), f"{label}: {name('length')} must be a number of seconds above 0")
        elif template is not None or (engine is not None and engine != HTML):
            err(p + ("length",), f"{label}: only an HTML scene without a table takes {name('length')}")
        elif s.get("narration"):
            err(p + ("length",), f"{label}: a scene with {name('length')} is silent and has no narration; remove "
                                 f"{name('length')} to narrate it (a narrated scene lasts its narration)")
    if "ambience" in s:
        if not isinstance(s["ambience"], bool):
            err(p + ("ambience",), f"{label}: {name('ambience')} must be {name('ambience_values')}")
        elif engine != VIDEO or template is not None:
            err(p + ("ambience",), f"{label}: only {name('video_scene')} has {name('ambience')} (the video model's "
                                   "sound track)")

    if "show_author" in s and not isinstance(s["show_author"], bool):
        err(p + ("show_author",), f"{label}: {name('show_author')} must be {name('show_author_values')}")

    silent = (engine == CLIP or has_length) and template is None
    missing = f"{label}: missing {name('narration')} (only {name('silent_scene')} may have none)"
    narration = s.get("narration", [] if silent else None)
    if narration is None:
        err(p + ("narration",), missing)
        return
    if not isinstance(narration, list) or not all(_text(x) for x in narration):
        err(p + ("narration",), f"{label}: `narration` must be a list of non-empty sentences")
        return
    if not narration and not silent:
        err(p + ("narration",), missing)
    n = len(narration)
    beats = s.get("beats", [] if silent else None)
    if not isinstance(beats, list) or len(beats) != n or not all(_text(x) for x in beats):
        err(p + ("beats",), f"{label}: `beats` must be a list of {n} non-empty strings, one per sentence")
    if "speakers" in s:
        names_ = s["speakers"]
        if not isinstance(names_, list) or len(names_) != n:
            err(p + ("speakers",), f"{label}: `speakers` must be a list of {n} speaker names or nulls, one per "
                                   "sentence")
        else:
            for j, sp in enumerate(names_):
                if sp is not None and not (isinstance(sp, str) and sp in speakers):
                    err(p + ("speakers", j), f"{label} sentence {j + 1}: speaker {sp!r} is not defined; add it "
                                             f"to {name('speakers')} or {name('no_speaker')}")
    if "voices" in s:
        voices = s["voices"]
        if not isinstance(voices, list) or len(voices) != n:
            err(p + ("voices",), f"{label}: `voices` must be a list of {n} voice objects or nulls, one per "
                                 "sentence")
        else:
            for j, v in enumerate(voices):
                if v is not None:
                    _voice_fields(v, p + ("voices", j), f"{label} sentence {j + 1}", err)


def parse_json(text: str) -> dict:
    """Read storyboard.json into the storyboard dict, whitespace in every
    string collapsed as in storyboard.md. Raises StoryboardError listing every
    problem."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise StoryboardError(f"{JSON_FILE} line {e.lineno}: not valid JSON: {e.msg}") from None
    data = normalize(data)
    problems = check(data)
    if problems:
        raise StoryboardError("\n".join(f"{JSON_FILE}: {msg}" for _, msg in problems))
    for scene in data["scenes"]:  # a silent scene may leave both out
        scene.setdefault("narration", [])
        scene.setdefault("beats", [])
    return data


def to_json(data: dict) -> str:
    """The storyboard dict as storyboard.json text."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- Markdown -> dict --------------------------------------------------------


def _cells(line: str) -> list[str]:
    s = line.strip().removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [normalize(c.replace("\\|", "|")) for c in UNESCAPED_PIPE_RE.split(s)]


def _columns(cells: list[str]) -> tuple[list[str] | None, str | None]:
    """The scene table's columns, lowercase: optional Speaker, Narration, On
    screen, then any of Model, Voice, Speed, Style once each; or None and
    what is wrong with the header."""
    head = [c.lower() for c in cells]
    lead = 1 if head[:1] == ["speaker"] else 0
    extra = head[lead + 2:]
    if head[lead:lead + 2] != TABLE_HEADER:
        return None, ("the table header must be `| Narration | On screen |`, optionally with a Speaker column "
                      "first and any of Model, Voice, Speed, Style after On screen")
    unknown = [c for c in extra if c not in VOICE_COLUMNS]
    if OLD_VOICE_KEY in unknown:
        return None, f"table column 'Backend': {backend_moved()}"
    if unknown:
        return None, (f"unknown table column {cells[lead + 2 + extra.index(unknown[0])]!r}; after On screen "
                      "only Model, Voice, Speed, Style")
    repeated = [c for i, c in enumerate(extra) if c in extra[:i]]
    if repeated:
        return None, f"table column {COLUMN_TITLES[repeated[0]]!r} given twice"
    return head, None


@dataclass
class _Field:
    line: int
    parts: list[str]

    @property
    def value(self) -> str:
        return normalize(" ".join(self.parts))


@dataclass
class _Scene:
    line: int
    id: str
    fields: dict[str, _Field] = field(default_factory=dict)
    table: str | None = None  # None, "header", "rows", "rejected" (bad header), "done"
    columns: list[str] = field(default_factory=lambda: list(TABLE_HEADER))
    rows: list[tuple[dict[str, str], int]] = field(default_factory=list)  # cells by column, line
    bad_rows: bool = False
    preview: str | None = None


def _speed(cell: str, n: int, label: str, err) -> float | None:
    """A Speed cell as a number; empty is None."""
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        err(n, f"{label}: Speed {cell!r} is not a number")
        return None


def parse_markdown(text: str) -> dict:
    """Parse storyboard Markdown into the storyboard dict. Raises StoryboardError
    listing every problem with its line number: the Markdown syntax here, the
    structure by `check`."""
    errors: list[str] = []

    def err(line: int, msg: str) -> None:
        errors.append(f"{MD_FILE} line {line}: {msg}")

    title: str | None = None
    title_line = 1
    header: dict[str, _Field] = {}
    scenes_: list[_Scene] = []
    cur: _Scene | None = None
    open_field: _Field | None = None
    speakers_table: str | None = None  # the header's speakers table: None, "header", "rows", "done"
    speakers: dict[str, dict] = {}
    speaker_lines: dict[str, int] = {}

    in_comment = False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        # `<!-- ... -->` comments (one or several lines) are skipped entirely.
        if in_comment or line.startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if not line:
            open_field = None
            if cur is not None and cur.table is not None:
                cur.table = "done"
            if cur is None and speakers_table is not None:
                speakers_table = "done"
            continue

        if HEADING_RE.match(line):
            open_field = None
            level = len(line) - len(line.lstrip("#"))
            rest = line[level:].strip()
            if level == 1:
                if title is not None or scenes_:
                    err(n, "a second `# ` title; scenes start with `## <scene id>`")
                elif not rest:
                    err(n, "empty title")
                else:
                    title, title_line = normalize(rest), n
            elif level == 2:
                if title is None:
                    err(n, "the file must start with `# <title>`")
                cur = _Scene(n, rest)
                scenes_.append(cur)
            else:
                err(n, "only `# <title>` and `## <scene id>` headings are allowed")
            continue

        if title is None:
            err(n, "the file must start with `# <title>`")
            continue

        if line.startswith("|"):
            open_field = None
            cells = _cells(line)
            if cur is None:
                if speakers_table is None:
                    if OLD_VOICE_KEY in [c.lower() for c in cells]:
                        err(n, f"speakers table column 'Backend': {backend_moved()}")
                    elif [c.lower() for c in cells] != SPEAKERS_HEADER:
                        err(n, "table outside a scene; put it under a `## <scene id>` heading (the header "
                               "holds only the `| Speaker | Model | Voice | Speed | Style |` table)")
                    speakers_table = "header"
                elif speakers_table == "header":
                    if not all(SEPARATOR_CELL_RE.match(c) for c in cells) or len(cells) != 5:
                        err(n, "the second line of the speakers table must be `|---|---|---|---|---|`")
                    speakers_table = "rows"
                elif speakers_table == "rows":
                    _speaker_row(cells, n, speakers, speaker_lines, err)
                else:
                    err(n, "a second table in the header; the header holds one speakers table, "
                           "with no blank lines inside it")
                continue
            if cur.table is None:
                columns, problem = _columns(cells)
                if problem:
                    err(n, problem)
                    cur.table, cur.bad_rows = "rejected", True
                else:
                    cur.columns, cur.table = columns, "header"
            elif cur.table == "rejected":
                pass  # the rest of a table whose header is reported
            elif cur.table == "header":
                width = len(cur.columns)
                if not all(SEPARATOR_CELL_RE.match(c) for c in cells) or len(cells) != width:
                    err(n, f"the second table line must be `|{'---|' * width}`")
                cur.table = "rows"
            elif cur.table == "rows":
                width = len(cur.columns)
                row = dict(zip(cur.columns, cells))
                bad = len(cells) != width or not row["narration"] or not row["on screen"]
                cur.bad_rows = cur.bad_rows or bad
                if len(cells) != width:
                    err(n, f"table row has {len(cells)} cells, needs {width} "
                           f"({', '.join(COLUMN_TITLES[c] for c in cur.columns)}); write a literal | as \\|")
                elif not row["narration"]:
                    err(n, "empty Narration cell")
                elif not row["on screen"]:
                    err(n, "empty On screen cell")
                else:
                    cur.rows.append((row, n))
            else:
                err(n, f"scene {cur.id!r} already has its table; one table per scene, no blank lines inside it")
            continue

        src = preview_src(line)
        if src is not None:
            open_field = None
            if cur is None:
                err(n, "image preview outside a scene; put it in the scene, above its table")
            elif cur.table is not None:
                err(n, "image preview after the table; put it above the table")
            elif cur.preview is not None:
                err(n, f"scene {cur.id!r} already has an image preview")
            else:
                cur.preview = src
            continue

        m = KEY_RE.match(line)
        key = KNOWN_KEYS.get(m.group(1).lower(), m.group(1)) if m else None
        if m and " " in key and key not in KNOWN_KEYS.values():
            m = None  # "Two words:" that are not a key are text
        if m:
            value = m.group(2) or ""
            allowed = SCENE_KEYS if cur is not None else HEADER_KEYS
            target = cur.fields if cur is not None else header
            open_field = None
            if cur is None and key in MOVED_KEYS:
                err(n, f"`{key}:` is set in the project's settings.yaml (`{MOVED_KEYS[key]}:`), "
                       "not in the storyboard")
            elif key not in allowed:
                where = f"scene {cur.id!r}" if cur is not None else "the header"
                err(n, f"unknown key `{key}:` in {where}; allowed: {', '.join(k + ':' for k in allowed)}")
            elif cur is not None and cur.table is not None:
                err(n, f"`{key}:` after the table; put it above the table")
            elif key in target:
                err(n, f"`{key}:` given twice (first at line {target[key].line})")
            else:
                target[key] = open_field = _Field(n, [value])
            continue

        if open_field is not None:
            open_field.parts.append(line)
        elif cur is not None and cur.table is not None:
            err(n, "text after the table; every sentence goes in a table row")
        else:
            err(n, "text outside a field; start the line with a key such as `Brief:` "
                   "or join it to the field above without a blank line")

    if title is None and not errors:
        err(1, "the file must start with `# <title>`")

    # The dict, and the line of each part of it for the messages of `check`.
    lines: dict[tuple, int] = {("title",): title_line}
    data: dict = {"title": title or "", "topic": header["Topic"].value if "Topic" in header else ""}
    for key in HEADER_KEYS:
        if key in header:
            lines[(key.lower(),)] = header[key].line
    if "Source" in header:
        data["source"] = header["Source"].value
    if speakers:
        data["speakers"] = speakers
        lines.update({("speakers", sp): line for sp, line in speaker_lines.items()})
    data["scenes"] = []
    skip: set[tuple] = set() if title is not None else {("title",)}
    for i, s in enumerate(scenes_):
        p = ("scenes", i)
        lines[p] = s.line
        scene: dict = {"id": s.id}
        for key in ("Template", "Image", "Brief", "Engine", "Ambience", "Length", "World", "Show author"):
            if key in s.fields:
                value = s.fields[key].value
                if key == "Ambience":
                    value = AMBIENCE_VALUES.get(value.lower(), value)
                elif key == "Show author":
                    value = SHOW_AUTHOR_VALUES.get(value.lower(), value)
                elif key == "Length":
                    value = _seconds(value)
                k = key.lower().replace(" ", "_")
                scene[k] = value
                lines[p + (k,)] = s.fields[key].line
        if s.preview is not None:
            scene["preview"] = s.preview
        scene["narration"] = [r["narration"] for r, _ in s.rows]
        scene["beats"] = [r["on screen"] for r, _ in s.rows]
        if "speaker" in s.columns:
            scene["speakers"] = [r["speaker"] or None for r, _ in s.rows]
        extra = [c for c in s.columns if c in VOICE_COLUMNS]
        if extra:
            scene["voices"] = []
            for j, (r, line) in enumerate(s.rows, 1):
                v = {VOICE_COLUMNS[c]: r[c] for c in extra if r[c]}
                if "speed" in v:
                    v["speed"] = _speed(v["speed"], line, f"scene {s.id!r} sentence {j}", err)
                scene["voices"].append(v or None)
        for j, (_, line) in enumerate(s.rows):
            for key in ("narration", "beats", "speakers", "voices"):
                lines[p + (key, j)] = line
        if s.table is not None and not s.rows:
            skip.add(p + ("narration",))
            if not s.bad_rows:
                err(s.line, f"scene {s.id!r}: the table has no rows")
        data["scenes"].append(scene)

    for path, msg in check(data, MD_NAMES):
        if path not in skip:
            at = next((lines[path[:k]] for k in range(len(path), 0, -1) if path[:k] in lines), title_line)
            err(at, msg)
    if errors:
        raise StoryboardError("\n".join(sorted(errors, key=_line_of)))
    return data


def _seconds(value: str) -> float | str:
    """A `Length:` value as a number of seconds (an optional trailing `s`); the text itself when it is not one,
    for `check` to report."""
    try:
        return float(value.removesuffix("s").strip())
    except ValueError:
        return value


def _line_of(message: str) -> int:
    m = re.match(rf"{re.escape(MD_FILE)} line (\d+):", message)
    return int(m.group(1)) if m else 0


def _speaker_row(cells: list[str], n: int, speakers: dict, lines: dict, err) -> None:
    """Add one row of the header's speakers table to `speakers`."""
    if len(cells) != 5:
        err(n, f"speakers table row has {len(cells)} cells, needs 5 (Speaker, Model, Voice, Speed, Style)")
        return
    name, model, voice, speed, style = cells
    if name in lines:
        err(n, f"duplicate speaker {name!r} (first at line {lines[name]})")
        return
    lines[name] = n
    speakers[name] = {"model": model or None, "name": voice or None,
                      "speed": _speed(speed, n, f"speaker {name!r}", err), "style": style or None}


def resolve_voice(data: dict, speaker: str | None = None, own: dict | None = None) -> dict:
    """A voice as `model`, `name`, `speed`, `style`: the speaker's (speaker
    None: `voice:` from the settings), with the set fields of `own` (a
    sentence's settings) over it, then a null `speed` filled in as 1.0. A null
    `model` is the `speech` model of config.yaml and a null `name` the model's
    default voice, both as the voiceover skill resolves them. An own `model`
    that differs from the speaker's drops the speaker's `name`."""
    v = settings.get()["voice"]
    src = v if speaker is None else (data.get("speakers") or {})[speaker]
    merged = {k: src.get(k) for k in VOICE_KEYS}
    own = {k: x for k, x in (own or {}).items() if x not in (None, "")}
    if own.get("model", merged["model"]) != merged["model"]:
        merged["name"] = None  # another model: its default voice unless `own` names one
    merged.update(own)
    speed = merged["speed"]
    return {"model": merged["model"] or None, "name": merged["name"] or None,
            "speed": 1.0 if speed is None else speed, "style": merged["style"] or None}


def sentence_voices(data: dict, scene: dict) -> list[dict]:
    """The resolved voice of each sentence of a scene: its speaker's voice
    with the sentence's own settings (`voices`) over it."""
    n = len(scene.get("narration") or [])
    return [resolve_voice(data, sp, own) for sp, own in
            zip(scene.get("speakers") or [None] * n, scene.get("voices") or [None] * n)]


def json_template(title: str, images: list[str], silent: bool = False, length: float | None = None) -> str:
    """Starting storyboard.json written by `init --json`: the starting
    storyboard.md as a dict, without its image previews."""
    data = parse_markdown(template(title, images, silent, length))
    for scene in data["scenes"]:
        scene.pop("preview", None)
    return to_json(data)


# Length of the one scene of `init --silent` without --length.
SILENT_SCENE_SECONDS = 10.0


def silent_template(title: str, images: list[str], length: float | None = None) -> str:
    """Starting storyboard.md written by `init --silent`: `assets/storyboard-silent.md` with one silent scene
    (`assets/storyboard-scene-silent.md`) per image, or one scene without images. `length` is shared among the
    scenes in tenths of a second, the last taking the remainder, so the Lengths sum to it."""
    s = settings.get()["storyboard"]
    ids = [s["image_scene_id"].format(n=i) for i in range(1, len(images) + 1)] or ["scene_1"]
    total = round((length or SILENT_SCENE_SECONDS * len(ids)) * 10)
    tenths = [total // len(ids)] * (len(ids) - 1)
    tenths.append(total - sum(tenths))
    blocks = []
    for i, sid in enumerate(ids):
        image = f"Image: {images[i]}\n" if images else ""
        blocks.append(settings.asset("storyboard-scene-silent.md").strip()
                      .replace("__SCENE_ID__", sid).replace("__IMAGE_LINE__", image)
                      .replace("__LENGTH__", f"{tenths[i] / 10:g}"))
    return (settings.asset("storyboard-silent.md")
            .replace("__TITLE__", title)
            .replace("__SCENES__", "\n\n".join(blocks)))


def template(title: str, images: list[str], silent: bool = False, length: float | None = None) -> str:
    """Starting storyboard.md written by `init`: `assets/storyboard.md` with
    one `assets/storyboard-scene.md` section per image (none without images);
    with `silent`, `silent_template`."""
    if silent:
        return silent_template(title, images, length)
    s = settings.get()["storyboard"]
    blocks = []
    for i, image in enumerate(images, 1):
        blocks.append(settings.asset("storyboard-scene.md").strip()
                      .replace("__SCENE_ID__", s["image_scene_id"].format(n=i))
                      .replace("__IMAGE__", image)
                      .replace("__PREVIEW_WIDTH__", str(s["preview_width"])))
    return (settings.asset("storyboard.md")
            .replace("__TITLE__", title)
            .replace("__IMAGE_SCENES__\n\n", "".join(b + "\n\n" for b in blocks)))


def with_author(data: dict, author: str | None) -> dict:
    """Copy the film's author into every template scene (`card.js` shows it)."""
    if author:
        for s in data["scenes"]:
            if s.get("template") is not None:
                s["author"] = author
    return data


def source_file(project_dir: Path) -> Path:
    """The project's storyboard file: storyboard.md or storyboard.json. Raises
    StoryboardError when there is neither, or both."""
    found = [project_dir / f for f in (MD_FILE, JSON_FILE) if (project_dir / f).is_file()]
    if len(found) == 2:
        raise StoryboardError(f"{project_dir} has both {MD_FILE} and {JSON_FILE}; keep one of them")
    if not found:
        raise StoryboardError(f"{project_dir / MD_FILE} not found (nor {JSON_FILE})")
    return found[0]


def read(project_dir: Path) -> dict:
    """The storyboard dict from the project's storyboard file, as storyboard.json stores it."""
    path = source_file(project_dir)
    text = path.read_text(encoding="utf-8")
    return parse_markdown(text) if path.name == MD_FILE else parse_json(text)


def load(project_dir: Path) -> dict:
    """The storyboard dict, with the author from the settings added to template scenes."""
    return with_author(read(project_dir), settings.author())


def image_path(project_dir: Path, image: str) -> Path:
    """Resolve a scene's `image` (relative to `images/`; a leading `images/` is allowed)."""
    rel = image[len("images/"):] if image.startswith("images/") else image
    return project_dir / "images" / rel


def show_author(scene: dict) -> bool:
    """Whether the film's creator caption is drawn over the scene: the scene's
    own `show_author` when set, else its template's `show_author` rule, else
    True."""
    if "show_author" in scene:
        return scene["show_author"]
    t = scene.get("template")
    return bool(_templates().get(t, {}).get("show_author", True)) if t else True


def scenes(data: dict) -> list[dict]:
    return list(data.get("scenes") or [])


def scene_by_id(data: dict, scene_id: str) -> dict:
    for s in scenes(data):
        if s.get("id") == scene_id:
            return s
    raise StoryboardError(f"scene {scene_id!r} is not in the storyboard")


def is_clip(scene: dict) -> bool:
    return scene.get("engine") == CLIP


def is_video(scene: dict) -> bool:
    return scene.get("engine") == VIDEO


def is_presenter(scene: dict) -> bool:
    return scene.get("engine") == PRESENTER


def narrated(scene: dict) -> bool:
    """False for a scene without a table (a clip scene, or an HTML scene with `length`), which is silent."""
    return bool(scene.get("narration"))


def length_seconds(scene: dict) -> float | None:
    """The `length` of a silent HTML scene, or None."""
    return float(scene["length"]) if scene.get("length") is not None else None


def world_name(scene: dict) -> str | None:
    """The scene's `world`, or None."""
    return scene.get("world")


def world_scenes(data: dict, name: str) -> list[dict]:
    """The scenes of world `name`, in film order."""
    return [s for s in scenes(data) if s.get("world") == name]


def world_of(data: dict, scene: dict) -> list[dict] | None:
    """The scenes of the scene's world, in film order, or None for a scene in no world."""
    name = world_name(scene)
    return world_scenes(data, name) if name else None


def clip_seconds(project_dir: Path | None, scene: dict) -> float | None:
    """Length of the latest imported clip of a scene (`clip_duration` in its
    `meta.json`), or None."""
    if project_dir is None:
        return None
    sdir = state.latest_render(project_dir, scene["id"])
    meta = state.read_meta(sdir) if sdir is not None else None
    return float(meta["clip_duration"]) if meta and meta.get("engine") == CLIP else None


def with_clip(scene: dict, project_dir: Path | None, seconds: float) -> float:
    """A scene's length from its narration `seconds`: a clip scene lasts at
    least its imported clip."""
    t = clip_seconds(project_dir, scene) if is_clip(scene) else None
    return seconds if t is None else max(seconds, t)


def estimate_seconds(data: dict, project_dir: Path | None = None) -> float:
    """Each scene's narration word count at `length.words_per_second`; a clip
    scene counts at least its imported clip's length, a clip scene without
    narration and no imported clip `length.clip_seconds`, a silent HTML scene
    its `length`."""
    length = settings.get()["length"]
    total = 0.0
    for s in scenes(data):
        words = sum(len(str(line).split()) for line in s.get("narration") or [])
        seconds = words / length["words_per_second"]
        if is_clip(s) and not narrated(s) and clip_seconds(project_dir, s) is None:
            seconds = float(length["clip_seconds"])
        if length_seconds(s) is not None:
            seconds = length_seconds(s)
        total += with_clip(s, project_dir, seconds)
    return total


def _same_file(project_dir: Path, preview: str, image: Path) -> bool:
    """True when the preview path (relative to storyboard.md) is the scene's image."""
    p = project_dir / preview
    return p.is_file() and p.resolve() == image.resolve()


def voice_errors(voice: dict, label) -> list[str]:
    """Problems of one voice (`model`, `speed`) under the rules of `voice:` in
    the settings; `label(key)` names a field in the messages. Whether the model
    takes the speed and the style, the voiceover skill checks when it voices."""
    rules = settings.get()["voice"]
    out = []
    model = voice.get("model")
    if model is not None and (not isinstance(model, str) or ":" not in model.strip(":")):
        out.append(f"{label('model')} must be a speech model id <provider>:<model> of config.yaml, or empty for "
                   "its `speech` model")
    speed = voice.get("speed")
    if not _number(speed) or not rules["speed_min"] <= speed <= rules["speed_max"]:
        out.append(f"{label('speed')} must be a number between {rules['speed_min']} and {rules['speed_max']}")
    return out


def validate_settings(project_dir: Path, brand_dir: Path | None = None) -> Validation:
    """Check the author, voice, music, critic, template and brand values in the settings;
    `brand_dir` is the brand folder given as `--brand`."""
    r = Validation()
    err = r.errors.append
    s = settings.get()

    a = s.get("author")
    if a is not None and not isinstance(a, (str, list)):
        err("`author` must be a list of names")
    elif not settings.authors():
        r.warnings.append(f"no `author:` in {settings.PROJECT_FILE}: the film has no creator credit")

    if s["voice"].get(OLD_VOICE_KEY) is not None:
        err(f"`voice.backend` is no longer read: {backend_moved(str(s['voice'][OLD_VOICE_KEY]))}")
    r.errors.extend(voice_errors(s["voice"], lambda key: f"`voice.{key}`"))
    gap = s["voice"].get("speaker_gap")
    if not _number(gap) or gap < 0:
        err("`voice.speaker_gap` must be a number of seconds, 0 or more")

    m = s["music"]
    if m.get("prompt"):
        err("`music.prompt` is no longer read: make the track with the music skill and set `music.file`")
    if m.get("file") and not (project_dir / str(m["file"])).is_file():
        err(f"music file {m['file']!r} does not exist (relative to the project)")
    c = s.get("critic") or {}
    if "claude" in c:
        r.warnings.append("`critic.claude` is no longer read: the scene critic was removed; delete the key")
    if c.get("model") is not None and not (isinstance(c["model"], str) and c["model"].strip()):
        err("`critic.model` must be a model name or null")
    for key, default in (("rounds", 1), ("max_findings", 5), ("scene_max_findings", 5)):
        v = c.get(key, default)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            err(f"`critic.{key}` must be a whole number, 1 or more")
    for name, rule in (s.get("templates") or {}).items():
        if isinstance(rule, dict) and OLD_TEMPLATE_KEY in rule:
            err(f"`templates.{name}.{OLD_TEMPLATE_KEY}` is no longer read: it became `show_author` with the "
                f"inverted meaning (`{OLD_TEMPLATE_KEY}: true` is `show_author: false`); rename it in "
                f"{settings.PROJECT_FILE}")
    r.warnings.extend(brand.problems(s.get("brand"), brand_dir))
    return r


def clip_problem(project_dir: Path, scene: dict) -> str | None:
    """Why a clip scene's latest version cannot be assembled as it stands, or None."""
    sdir = state.latest_render(project_dir, scene["id"])
    meta = state.read_meta(sdir) if sdir is not None else None
    if meta is None or meta.get("engine") != CLIP:
        return ("no clip imported yet; make it at the `video:` size and fps and import it with `clip`")
    v = settings.get()["video"]
    if (meta.get("width"), meta.get("height"), meta.get("fps")) != (v["width"], v["height"], v["fps"]):
        return (f"the imported clip is {meta.get('width')}x{meta.get('height')} at {meta.get('fps')} fps, "
                f"`video:` is {v['width']}x{v['height']} at {v['fps']} fps; make the clip again and import it")
    if narrated(scene) and state.latest_voice(project_dir, scene["id"]) is None:
        return "no voice version yet; run `script`, voice it and run `voice`, then `clip` again"
    if narrated(scene) and meta.get("voice_version") is None:
        return "the clip was imported without narration; run `clip` again to mux the voice"
    latest = state.latest_voice(project_dir, scene["id"]) if narrated(scene) else None
    if latest is not None and meta.get("voice_version") != latest.name:
        return (f"the clip was muxed with voice {meta.get('voice_version')}, the latest voice version is "
                f"{latest.name}; run `clip` again")
    if not narrated(scene) and meta.get("voice_version") is not None:
        return "the scene has no narration now; run `clip` again"
    return None


def validate(data: dict, project_dir: Path, brand_dir: Path | None = None) -> Validation:
    """What `check` cannot check: files exist, the settings' voice, the
    speakers' voices and each sentence's own voice settings, music, author and
    brand (`brand_dir`, the `--brand` folder), image previews (storyboard.md
    only), template positions and row counts, and the length estimate."""
    r = validate_settings(project_dir, brand_dir)
    err, warn = r.errors.append, r.warnings.append

    source = data.get("source")
    if source:
        rel = source[len("sources/"):] if source.startswith("sources/") else source
        if not (project_dir / "sources" / rel).is_file():
            err(f"source file sources/{rel} does not exist")

    for name in data.get("speakers") or {}:
        r.errors.extend(voice_errors(resolve_voice(data, name), lambda key, name=name: f"speaker {name!r}: {key}"))
    for s in scenes(data):
        for j, (own, voice) in enumerate(zip(s.get("voices") or [], sentence_voices(data, s)), 1):
            if own:
                r.errors.extend(voice_errors(voice, lambda key, sid=s["id"], j=j: f"scene {sid} sentence {j}: {key}"))
    markdown = source_file(project_dir).name == MD_FILE

    templates = _templates()
    sc = scenes(data)
    for i, s in enumerate(sc, 1):
        label = f"scene {s['id']}"
        image = s.get("image")
        if image:
            path = image_path(project_dir, image)
            if not path.is_file():
                err(f"{label}: image {image!r} not found under images/")
            elif markdown and s.get("preview") is None:
                warn(f"{label}: no image preview; add `{preview_line(image)}` above the table")
            elif markdown and not _same_file(project_dir, s["preview"], path):
                warn(f"{label}: the image preview {s['preview']!r} is not the scene's image {image!r}")

        template = s.get("template")
        if template is not None:
            rules = templates.get(template, {})
            if rules.get("position") == "first" and i != 1:
                warn(f"{label}: the {template} scene is usually the first scene")
            if rules.get("position") == "last" and i != len(sc):
                warn(f"{label}: the {template} scene is usually the last scene")
            limit = rules.get("max_rows")
            if limit and len(s["narration"]) > limit:
                warn(f"{label}: a {template} scene usually has at most {limit} rows; check that the text fits")

        if is_clip(s):
            warn_clip = clip_problem(project_dir, s)
            if warn_clip:
                warn(f"{label}: {warn_clip}")

    for name in dict.fromkeys(w for s in sc if (w := world_name(s))):
        members = world_scenes(data, name)
        if len(members) == 1:
            warn(f"scene {members[0]['id']}: world {name!r} has one scene; a world joins consecutive scenes "
                 "without a cut, so drop `World:` or add the scenes that follow")

    length = settings.get()["length"]
    r.estimated_seconds = estimate_seconds(data, project_dir)
    if not length["min_seconds"] <= r.estimated_seconds <= length["max_seconds"]:
        warn(f"estimated length {r.estimated_seconds:.0f} s is outside {length['min_seconds']}-"
             f"{length['max_seconds']} s (at {length['words_per_second']} words per second)")
    return r
