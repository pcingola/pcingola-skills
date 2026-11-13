"""Parse and validate `storyboard.md`.

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

    | Speaker | Backend | Voice | Speed | Style |
    |---|---|---|---|---|
    | guest | speech | Kore | 1.0 | warm, curious |

A scene table may then start with a Speaker column,
`| Speaker | Narration | On screen |`, whose cells name a speaker of that
table; an empty cell is the default voice.

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
header has a speakers table (name to `backend`, `name`, `speed`, `style`,
an empty cell as None) and `scenes`. Each scene:
`id` (`[a-z0-9_]+`, unique), `image` (path under `images/`), `brief`,
`narration` (list of sentences) and `beats` (same length as `narration`). A
scene whose table has the Speaker column also has `speakers`, the Speaker
cell of each sentence (None when empty). A
template scene has `template` instead of `brief` and `image` only when given;
`load` adds a copy of the film's author (from settings) when one is set, for
the scene's `card.js`.

A scene may name its engine with `Engine: html` (the default, HyperFrames) or
`Engine: manim` (a Manim Community Edition `scene.py`, see `manim_scene`). A
manim scene needs `Brief:`, its `Image:` is optional, and it cannot be a
template scene. The parsed scene has `engine` only when `Engine:` is given,
and a manim scene has `image` only when given.

`Engine: clip` marks a scene whose video is a clip made outside short-video and
imported with `clip` (see `clip`). Its `Brief:` and
`Image:` are optional (the parsed scene has `brief` and `image` only when
given), and it cannot be a template scene. Only a clip scene may have no
table: its `narration` and `beats` are then empty, and the scene is silent
and lasts its clip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import brand, settings, state

MD_FILE = "storyboard.md"
SCENE_ID_RE = re.compile(r"^[a-z0-9_]+$")

HEADER_KEYS = ("Topic", "Source")
# Header keys of older storyboards and where their values live now.
MOVED_KEYS = {"Voice": "voice", "Music": "music", "Author": "author"}
SCENE_KEYS = ("Image", "Brief", "Template")
SCENE_KEYS = SCENE_KEYS + ("Engine",)
# Values of a scene's `Engine:` key; a scene without one uses the first.
ENGINES = ("html", "manim", "clip")
CLIP = "clip"
TABLE_HEADER = ["narration", "on screen"]
# A scene table with the optional Speaker column.
SPEAKER_TABLE_HEADER = ["speaker"] + TABLE_HEADER
# The header's speakers table.
SPEAKERS_HEADER = ["speaker", "backend", "voice", "speed", "style"]
KEY_RE = re.compile(r"^([A-Z][A-Za-z]*):(?:\s+(.*))?$")
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
    """Template scenes and their rules (position, max_rows, shows_author, hold_seconds)."""
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


# --- Markdown -> dict --------------------------------------------------------


def _cells(line: str) -> list[str]:
    s = line.strip().removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [normalize(c.replace("\\|", "|")) for c in UNESCAPED_PIPE_RE.split(s)]


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
    table: str | None = None  # None, "header", "rows", "done"
    columns: int = 2  # 3 with the Speaker column
    rows: list[tuple[str, str, str | None, int]] = field(default_factory=list)  # narration, on screen, speaker, line
    bad_rows: bool = False
    preview: str | None = None


def parse_markdown(text: str) -> dict:
    """Parse storyboard Markdown into the storyboard dict. Raises StoryboardError
    listing every problem with its line number."""
    errors: list[str] = []

    def err(line: int, msg: str) -> None:
        errors.append(f"{MD_FILE} line {line}: {msg}")

    title: str | None = None
    title_line = 1
    header: dict[str, _Field] = {}
    scenes_: list[_Scene] = []
    seen_ids: dict[str, int] = {}
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

        if line.startswith("#"):
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
                if not SCENE_ID_RE.match(rest):
                    err(n, f"invalid scene id {rest!r}: use lowercase letters, digits and _ only")
                elif rest in seen_ids:
                    err(n, f"duplicate scene id {rest!r} (first at line {seen_ids[rest]})")
                else:
                    seen_ids[rest] = n
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
                    if [c.lower() for c in cells] != SPEAKERS_HEADER:
                        err(n, "table outside a scene; put it under a `## <scene id>` heading (the header "
                               "holds only the `| Speaker | Backend | Voice | Speed | Style |` table)")
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
                head = [c.lower() for c in cells]
                if head == SPEAKER_TABLE_HEADER:
                    cur.columns = 3
                elif head != TABLE_HEADER:
                    err(n, "the table header must be `| Narration | On screen |` "
                           "or `| Speaker | Narration | On screen |`")
                cur.table = "header"
            elif cur.table == "header":
                if not all(SEPARATOR_CELL_RE.match(c) for c in cells) or len(cells) != cur.columns:
                    err(n, f"the second table line must be `|{'---|' * cur.columns}`")
                cur.table = "rows"
            elif cur.table == "rows":
                names = "Speaker, Narration, On screen" if cur.columns == 3 else "Narration, On screen"
                cur.bad_rows = cur.bad_rows or len(cells) != cur.columns or not all(cells[-2:])
                if len(cells) != cur.columns:
                    err(n, f"table row has {len(cells)} cells, needs {cur.columns} ({names}); "
                           "write a literal | as \\|")
                elif not cells[-2]:
                    err(n, "empty Narration cell")
                elif not cells[-1]:
                    err(n, "empty On screen cell")
                else:
                    cur.rows.append((cells[-2], cells[-1], cells[0] if cur.columns == 3 else None, n))
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
        if m:
            key, value = m.group(1), m.group(2) or ""
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
    if "Topic" not in header or not header["Topic"].value:
        err(header["Topic"].line if "Topic" in header else title_line, "missing `Topic:` paragraph")
    if not scenes_:
        err(title_line, "no scenes; add a `## <scene id>` section")

    data: dict = {"title": title or "", "topic": header["Topic"].value if "Topic" in header else ""}
    if "Source" in header:
        data["source"] = header["Source"].value
    if speakers:
        data["speakers"] = speakers

    templates = _templates()
    data["scenes"] = []
    for s in scenes_:
        value = {k: f.value for k, f in s.fields.items()}
        engine = value.get("Engine")
        if engine is not None and engine not in ENGINES:
            err(s.fields["Engine"].line, f"`Engine:` must be one of {', '.join(ENGINES)}")
        if engine is not None and "Template" in s.fields:
            err(s.fields["Engine"].line, f"scene {s.id!r}: a template scene takes no `Engine:`")
        template = value.get("Template")
        if template is not None:
            if template not in templates:
                err(s.fields["Template"].line, f"`Template:` must be one of {', '.join(templates)}")
            if "Brief" in s.fields:
                err(s.fields["Brief"].line, f"scene {s.id!r}: a template scene takes no `Brief:`")
        elif engine == "manim":
            if not value.get("Brief"):
                err(s.line, f"scene {s.id!r}: missing `Brief:` line")
        elif engine == CLIP:
            pass
        else:
            for key in ("Image", "Brief"):
                if not value.get(key):
                    err(s.line, f"scene {s.id!r}: missing `{key}:` line")
        if s.table is None:
            if engine != CLIP or template is not None:
                err(s.line, f"scene {s.id!r}: missing the `| Narration | On screen |` table "
                            "(only an `Engine: clip` scene may have none)")
        elif not s.rows and not s.bad_rows:
            err(s.line, f"scene {s.id!r}: the table has no rows")
        scene: dict = {"id": s.id}
        if template is not None:
            scene["template"] = template
            if value.get("Image"):
                scene["image"] = value["Image"]
        elif engine == "manim":
            if value.get("Image"):
                scene["image"] = value["Image"]
            scene["brief"] = value.get("Brief", "")
        elif engine == CLIP:
            for key in ("Image", "Brief"):
                if value.get(key):
                    scene[key.lower()] = value[key]
        else:
            scene["image"] = value.get("Image", "")
            scene["brief"] = value.get("Brief", "")
        if engine is not None and template is None:
            scene["engine"] = engine
        if s.preview is not None:
            scene["preview"] = s.preview
        scene["narration"] = [r[0] for r in s.rows]
        scene["beats"] = [r[1] for r in s.rows]
        if s.columns == 3:
            scene["speakers"] = [r[2] or None for r in s.rows]
            for _, _, name, line in s.rows:
                if name and name not in speakers:
                    err(line, f"speaker {name!r} is not defined; add it to the speakers table in the header "
                              "(`| Speaker | Backend | Voice | Speed | Style |`) or leave the cell empty "
                              "for the default voice")
        data["scenes"].append(scene)

    if errors:
        raise StoryboardError("\n".join(errors))
    return data


def _speaker_row(cells: list[str], n: int, speakers: dict, lines: dict, err) -> None:
    """Add one row of the header's speakers table to `speakers`."""
    if len(cells) != 5:
        err(n, f"speakers table row has {len(cells)} cells, needs 5 (Speaker, Backend, Voice, Speed, Style)")
        return
    name, backend, voice, speed, style = cells
    if not SCENE_ID_RE.match(name):
        err(n, f"invalid speaker name {name!r}: use lowercase letters, digits and _ only")
        return
    if name in lines:
        err(n, f"duplicate speaker {name!r} (first at line {lines[name]})")
        return
    lines[name] = n
    value: float | None = None
    if speed:
        try:
            value = float(speed)
        except ValueError:
            err(n, f"speaker {name!r}: Speed {speed!r} is not a number")
    speakers[name] = {"backend": backend or None, "name": voice or None, "speed": value, "style": style or None}


def speaker_voice(data: dict, name: str | None) -> dict:
    """The voice of a speaker as `backend`, `name`, `speed`, `style`, with
    defaults filled in: speaker None is `voice:` from the settings, a null
    `name` the backend's default voice from `voice.names`, a null `speed` 1.0."""
    v = settings.get()["voice"]
    src = v if name is None else (data.get("speakers") or {})[name]
    backend = src.get("backend")
    speed = src.get("speed")
    return {"backend": backend, "name": src.get("name") or (v.get("names") or {}).get(backend),
            "speed": 1.0 if speed is None else speed, "style": src.get("style") or None}


def template(title: str, images: list[str]) -> str:
    """Starting storyboard.md written by `init`: `assets/storyboard.md` with
    one `assets/storyboard-scene.md` section per image (none without images)."""
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


def load(project_dir: Path) -> dict:
    """Parse `storyboard.md`, with the author from the settings added."""
    md = project_dir / MD_FILE
    if not md.is_file():
        raise StoryboardError(f"{md} not found")
    return with_author(parse_markdown(md.read_text(encoding="utf-8")), settings.author())


def image_path(project_dir: Path, image: str) -> Path:
    """Resolve a scene's `image` (relative to `images/`; a leading `images/` is allowed)."""
    rel = image[len("images/"):] if image.startswith("images/") else image
    return project_dir / "images" / rel


def shows_author(scene: dict) -> bool:
    """True for a template scene whose page shows the author itself."""
    t = scene.get("template")
    return bool(t and _templates().get(t, {}).get("shows_author"))


def scenes(data: dict) -> list[dict]:
    return list(data.get("scenes") or [])


def scene_by_id(data: dict, scene_id: str) -> dict:
    for s in scenes(data):
        if s.get("id") == scene_id:
            return s
    raise StoryboardError(f"scene {scene_id!r} is not in the storyboard")


def is_clip(scene: dict) -> bool:
    return scene.get("engine") == CLIP


def narrated(scene: dict) -> bool:
    """False for a clip scene without a table, which is silent."""
    return bool(scene.get("narration"))


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
    narration and no imported clip `length.clip_seconds`."""
    length = settings.get()["length"]
    total = 0.0
    for s in scenes(data):
        words = sum(len(str(line).split()) for line in s.get("narration") or [])
        seconds = words / length["words_per_second"]
        if is_clip(s) and not narrated(s) and clip_seconds(project_dir, s) is None:
            seconds = float(length["clip_seconds"])
        total += with_clip(s, project_dir, seconds)
    return total


def _same_file(project_dir: Path, preview: str, image: Path) -> bool:
    """True when the preview path (relative to storyboard.md) is the scene's image."""
    p = project_dir / preview
    return p.is_file() and p.resolve() == image.resolve()


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def voice_errors(voice: dict, label) -> list[str]:
    """Problems of one voice (`backend`, `speed`, `style`) under the rules of
    `voice:` in the settings; `label(key)` names a field in the messages."""
    rules = settings.get()["voice"]
    names = rules.get("names") or {}
    styles = rules.get("style_backends") or []
    out = []
    if voice.get("backend") not in names:
        out.append(f"{label('backend')} must be one of {', '.join(sorted(names))}")
    if voice.get("style") and voice.get("backend") not in styles:
        out.append(f"{label('style')} needs one of these backends: {', '.join(styles)}")
    speed = voice.get("speed")
    if not _number(speed) or not rules["speed_min"] <= speed <= rules["speed_max"]:
        out.append(f"{label('speed')} must be a number between {rules['speed_min']} and {rules['speed_max']}")
    elif speed != 1.0 and voice.get("backend") in names and voice.get("backend") not in (rules.get("speed_backends") or []):
        out.append(f"{label('speed')} must be 1.0 for {voice['backend']}, which has no speed setting")
    return out


def validate_settings(project_dir: Path, brand_dir: Path | None = None) -> Validation:
    """Check the author, voice, music, critic and brand values in the settings;
    `brand_dir` is the brand folder given as `--brand`."""
    r = Validation()
    err = r.errors.append
    s = settings.get()

    a = s.get("author")
    if a is not None and not isinstance(a, (str, list)):
        err("`author` must be a list of names")
    elif not settings.authors():
        r.warnings.append(f"no `author:` in {settings.PROJECT_FILE}: `assemble` refuses to build the film without one")

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
    if not isinstance(c.get("claude", True), bool):
        err("`critic.claude` must be true or false")
    if c.get("model") is not None and not (isinstance(c["model"], str) and c["model"].strip()):
        err("`critic.model` must be a model name or null")
    r.warnings.extend(brand.problems(s.get("brand"), brand_dir))
    return r


def _clip_problem(project_dir: Path, scene: dict) -> str | None:
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
    """What `parse_markdown` cannot check: files exist, the settings' voice and
    the speakers' voices,
    music, author and brand (`brand_dir`, the `--brand` folder), image previews, template positions and row counts, and
    the length estimate."""
    r = validate_settings(project_dir, brand_dir)
    err, warn = r.errors.append, r.warnings.append

    source = data.get("source")
    if source:
        rel = source[len("sources/"):] if source.startswith("sources/") else source
        if not (project_dir / "sources" / rel).is_file():
            err(f"source file sources/{rel} does not exist")

    for name in data.get("speakers") or {}:
        r.errors.extend(voice_errors(speaker_voice(data, name), lambda key, name=name: f"speaker {name!r}: {key}"))

    templates = _templates()
    sc = scenes(data)
    for i, s in enumerate(sc, 1):
        label = f"scene {s['id']}"
        image = s.get("image")
        if image:
            path = image_path(project_dir, image)
            if not path.is_file():
                err(f"{label}: image {image!r} not found under images/")
            elif s.get("preview") is None:
                warn(f"{label}: no image preview; add `{preview_line(image)}` above the table")
            elif not _same_file(project_dir, s["preview"], path):
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
            warn_clip = _clip_problem(project_dir, s)
            if warn_clip:
                warn(f"{label}: {warn_clip}")

    length = settings.get()["length"]
    r.estimated_seconds = estimate_seconds(data, project_dir)
    if not length["min_seconds"] <= r.estimated_seconds <= length["max_seconds"]:
        warn(f"estimated length {r.estimated_seconds:.0f} s is outside {length['min_seconds']}-"
             f"{length['max_seconds']} s (at {length['words_per_second']} words per second)")
    return r
