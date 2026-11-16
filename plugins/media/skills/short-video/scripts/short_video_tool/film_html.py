"""`html`: the film as one standalone HTML file, `film/html/v<N>/film.html`.

The file plays every scene in storyboard order from its page: the latest page
version of each HTML scene (`pages.scene_page`), and a world once, spanning
its scenes. A manim, video, presenter or clip scene plays its latest
`scene.mp4` as a `<video>`; one with no render shows a card with its id. The
player (`assets/film-player.html`) owns the clock and seeks each page with
`assets/film-scene.js`, which is inlined into every page.

Each page is inlined whole (`inline_page`): every local `<script src>` as an
inline script, every other local file the page names (pictures, videos,
fonts, stylesheets) as a data URI. A scene's narration (its page's voice
version) and the music `assemble` would use play in step, as MP3 data URIs. The file
plays from file:// on another machine; web fonts linked from the internet need
a connection, and a font installed on this machine is missing there: `html`
warns for each font stack whose first family no local `@font-face` file
embeds.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import tempfile
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from . import media, mix, scenes, settings, state, storyboard, versions
from .pages import INDEX, is_page_scene, scene_page
from .scenes import SceneError

FILM_HTML = "film.html"
MANIFEST = "manifest.json"
# Seconds a scene with nothing to show lasts when neither its voice nor its Length gives one.
MISSING_SECONDS = 3.0
MP3_BITRATE = "128k"


class Kind(StrEnum):
    PAGE = "page"
    VIDEO = "video"
    MISSING = "missing"


@dataclass
class SceneMark:
    """A scene inside a segment: its id, start in segment time, and length."""

    id: str
    start: float
    duration: float


@dataclass
class Track:
    """An audio file and where it plays in film time."""

    path: Path
    start: float
    duration: float
    volume: float = 1.0


@dataclass
class Segment:
    """One layer of the film: a page (one scene, or a world spanning several), a rendered video, or a card."""

    kind: Kind
    duration: float
    scenes: list[SceneMark]
    source: Path | None = None       # the page's version directory, or the scene.mp4
    label: str = ""
    tracks: list[Track] = field(default_factory=list)   # in segment time
    start: float = 0.0


# ---------------------------------------------------------------------------
# Inlining


_SCRIPT_SRC = re.compile(r"""<script\b([^>]*?)\bsrc\s*=\s*(["'])([^"']+)\2([^>]*)>\s*</script\s*>""", re.I | re.S)
_QUOTED = re.compile(r"""(["'])([^"'<>\s]+?)\1""")
_CSS_URL = re.compile(r"""url\(\s*([^)'"\s]+)\s*\)""")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
MIME = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
        ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".gif": "image/gif", ".json": "application/json"}


def local_file(base: Path, ref: str) -> Path | None:
    """The file `ref` names inside `base`, or None: no URL scheme, no absolute path, no fragment, no escape from
    `base`, not an HTML page."""
    if not ref or _SCHEME.match(ref) or ref.startswith(("/", "#", "//")):
        return None
    try:
        p = (base / ref).resolve()
    except (OSError, ValueError):
        return None
    root = base.resolve()
    if root not in p.parents or not p.is_file() or p.suffix.lower() in (".html", ".htm"):
        return None
    return p


def data_uri(path: Path) -> str:
    mime = MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def inline_script(text: str) -> str:
    """Script text safe inside `<script>`: `</script` cannot close it early."""
    return re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)


def _inline_refs(base: Path, html: str) -> str:
    def quoted(m: re.Match) -> str:
        p = local_file(base, m.group(2))
        return f"{m.group(1)}{data_uri(p)}{m.group(1)}" if p else m.group(0)

    def css(m: re.Match) -> str:
        p = local_file(base, m.group(1))
        return f'url("{data_uri(p)}")' if p else m.group(0)

    return _CSS_URL.sub(css, _QUOTED.sub(quoted, html))


def inline_page(base: Path, html: str, scene_script: str = "") -> str:
    """The page `html` of directory `base` with every local script inlined as text and every other local file it
    names as a data URI; `scene_script` goes before `</body>` (or at the end)."""
    out, pos = [], 0
    for m in _SCRIPT_SRC.finditer(html):
        out.append(_inline_refs(base, html[pos:m.start()]))
        p = local_file(base, m.group(3).removeprefix("./"))
        if p is None:
            out.append(m.group(0))
        else:
            attrs = " ".join((m.group(1) + m.group(4)).split())
            out.append(f"<script{' ' + attrs if attrs else ''}>{inline_script(p.read_text(encoding='utf-8'))}</script>")
        pos = m.end()
    out.append(_inline_refs(base, html[pos:]))
    page = "".join(out)
    if scene_script:
        tag = f"<script>{inline_script(scene_script)}</script>"
        i = page.lower().rfind("</body>")
        page = page[:i] + tag + page[i:] if i >= 0 else page + tag
    return page


# ---------------------------------------------------------------------------
# Fonts

_FONT_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)
_FACE_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_FACE_SRC = re.compile(r"""url\(\s*["']?([^)"']+)["']?\s*\)""", re.I)
# A font stack: a `font-family` declaration, or a custom property named --font... (used through var()).
_FONT_STACK = re.compile(r"(?:font-family|--font[\w-]*)\s*:\s*([^;}{]+)", re.I)
GENERIC_FAMILIES = frozenset({
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
    "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "inherit", "initial", "unset", "revert",
    "-apple-system", "blinkmacsystemfont"})


def _family(text: str) -> str:
    return text.strip().strip("\"'").strip().lower()


def embedded_families(base: Path, html: str) -> set[str]:
    """The families (lower case) of the page's `@font-face` rules whose `src` is a file inside `base`."""
    out = set()
    for block in _FONT_FACE.findall(html):
        fam = _FACE_FAMILY.search(block)
        if fam and any(local_file(base, u) for u in _FACE_SRC.findall(block)):
            out.add(_family(fam.group(1)))
    return out


def unembedded_fonts(base: Path, html: str) -> list[str]:
    """The first families of the page's font stacks that are not generic and that no local `@font-face` embeds, in
    page order: they fall back to another font on a machine without them installed."""
    embedded = embedded_families(base, html)
    out: list[str] = []
    for stack in _FONT_STACK.findall(_FONT_FACE.sub(" ", html)):
        first = stack.split(",")[0].strip()
        fam = _family(first)
        if not fam or first.lower().startswith("var(") or fam in GENERIC_FAMILIES or fam in embedded:
            continue
        name = first.strip().strip("\"'")
        if name not in out:
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# Segments


def _voice_track(project: Path, scene_id: str, voice_version: str | None, start: float) -> list[Track]:
    if not voice_version:
        return []
    wav = state.voice_root(project, scene_id) / voice_version / "narration.wav"
    if not wav.is_file():
        raise SceneError(f"{wav} missing")
    return [Track(wav, start, media.duration(wav))]


def _read(path: Path) -> str | None:
    return path.read_text().strip() if path.is_file() else None


def _missing_seconds(project: Path, scene: dict) -> float:
    if (length := storyboard.length_seconds(scene)) is not None:
        return length
    vdir = state.latest_voice(project, scene["id"])
    if vdir is not None and (vdir / "timing.json").is_file():
        return float(json.loads((vdir / "timing.json").read_text(encoding="utf-8"))["duration"])
    return MISSING_SECONDS


def _missing(project: Path, scene: dict, why: str) -> Segment:
    d = _missing_seconds(project, scene)
    return Segment(Kind.MISSING, d, [SceneMark(scene["id"], 0.0, d)], label=f"scene {scene['id']}: {why}")


def _font_warnings(label: str, page_dir: Path) -> list[str]:
    html = (page_dir / INDEX).read_text(encoding="utf-8")
    return [f"{label}: font {f!r} is not embedded; film.html shows another font on a machine without it. Copy an "
            f"OFL font file into the page's fonts/ and load it with @font-face" for f in unembedded_fonts(page_dir, html)]


def segments(project: Path, data: dict) -> tuple[list[Segment], list[str]]:
    """The film's segments in storyboard order, with their starts, a warning per scene shown as a card and per
    font a page names without embedding it."""
    out, warnings, done_worlds = [], [], set()
    for s in storyboard.scenes(data):
        sid = s["id"]
        name = storyboard.world_name(s)
        if name in done_worlds:
            continue
        if is_page_scene(s):
            try:
                page = scene_page(project, data, s)
            except SceneError as e:
                warnings.append(str(e))
                out.append(_missing(project, s, "no page; run scaffold"))
                continue
            if name:
                done_worlds.add(name)
                plan = json.loads((page.dir / "world.json").read_text(encoding="utf-8"))
                marks = [SceneMark(x["id"], float(x["start"]), float(x["duration"])) for x in plan["scenes"]]
                tracks = [t for x in plan["scenes"]
                          for t in _voice_track(project, x["id"], x.get("voice_version"), float(x["start"]))]
                out.append(Segment(Kind.PAGE, float(plan["duration"]), marks, page.dir, tracks=tracks))
                warnings += _font_warnings(f"world {name}", page.dir)
            else:
                tracks = _voice_track(project, sid, _read(page.dir / "voice_version"), 0.0)
                out.append(Segment(Kind.PAGE, page.duration, [SceneMark(sid, 0.0, page.duration)], page.dir,
                                   tracks=tracks))
                warnings += _font_warnings(f"scene {sid}", page.dir)
            continue
        sdir = state.latest_render(project, sid)
        if sdir is None or not (sdir / "scene.mp4").is_file():
            warnings.append(f"scene {sid}: no render; the film shows a card")
            out.append(_missing(project, s, "no render"))
            continue
        d = media.duration(sdir / "scene.mp4")
        out.append(Segment(Kind.VIDEO, d, [SceneMark(sid, 0.0, d)], sdir / "scene.mp4"))
    t = 0.0
    for seg in out:
        seg.start = t
        t += seg.duration
    return out, warnings


def music_track(project: Path, duration: float, music_version: str | None = None) -> Track | None:
    """The music `assemble` would use (`music_version`, else the latest when `music.file` is set), from 0 for at
    most the film's length, at `mix.music_db`; None for a film without music."""
    path = mix.music_source(project, music_version)[1]
    if path is None:
        return None
    return Track(path, 0.0, min(duration, media.duration(path)), 10 ** (settings.get()["mix"]["music_db"] / 20))


def mp3_uri(path: Path, tmp: Path) -> str:
    out = tmp / f"{len(list(tmp.iterdir()))}.mp3"
    media.run([media.which("ffmpeg"), "-y", "-v", "error", "-i", path, "-vn", "-c:a", "libmp3lame",
               "-b:a", MP3_BITRATE, out])
    return data_uri(out)


def script_json(value: object) -> str:
    """`value` as JSON safe inside `<script>`: every `<` escaped."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def film_data(project: Path, data: dict, segs: list[Segment], node_dir: Path,
              music_version: str | None = None) -> dict:
    """The `FILM` object of the player: size, length, segments with their inlined pages or videos, audio. A
    library or kit file a page loads and its version lacks is copied in from `node_dir` first, as `render` does."""
    v = settings.get()["video"]
    scene_js = settings.asset("film-scene.js")
    duration = sum(s.duration for s in segs)
    tracks = [Track(t.path, seg.start + t.start, t.duration, t.volume) for seg in segs for t in seg.tracks]
    if (m := music_track(project, duration, music_version)) is not None:
        tracks.append(m)
    items = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, seg in enumerate(segs):
            item = {"kind": seg.kind.value, "start": round(seg.start, 6), "duration": round(seg.duration, 6),
                    "scenes": [asdict(m) for m in seg.scenes], "label": seg.label}
            if seg.kind == Kind.PAGE:
                html = (seg.source / INDEX).read_text(encoding="utf-8")
                scenes.copy_page_files(seg.source, html, node_dir, missing_only=True)
                item["page"] = inline_page(seg.source, html, f"window.__FILM_INDEX = {k};\n" + scene_js)
            elif seg.kind == Kind.VIDEO:
                item["video"] = data_uri(seg.source)
            items.append(item)
        audio = [{"src": mp3_uri(t.path, Path(tmp)), "start": round(t.start, 6), "duration": round(t.duration, 6),
                  "volume": t.volume} for t in tracks]
    return {"title": data.get("title") or project.name, "width": v["width"], "height": v["height"],
            "duration": round(duration, 6), "segments": items, "audio": audio}


def build_html(film: dict) -> str:
    """film.html from the player asset and the `FILM` object."""
    title = re.sub(r"[<>&]", "", str(film["title"]))
    return (settings.asset("film-player.html").replace("__TITLE__", title)
            .replace("/*__FILM__*/null", script_json(film)))


def manifest(project: Path, segs: list[Segment], size: int) -> dict:
    return {"segments": [{"kind": s.kind.value, "start": round(s.start, 6), "duration": round(s.duration, 6),
                          "scenes": [m.id for m in s.scenes],
                          "source": str(s.source.relative_to(project)) if s.source else None,
                          "audio": [str(t.path.relative_to(project)) for t in s.tracks]} for s in segs],
            "bytes": size}


def write(project: Path, data: dict, node_dir: Path, out: Path | None = None,
          music_version: str | None = None) -> tuple[Path, list[str]]:
    """Write film.html (to `out`, else to the next `film/html/v<N>/`, with `manifest.json`). Returns (the file,
    warnings)."""
    segs, warnings = segments(project, data)
    if not segs:
        raise SceneError("the storyboard has no scenes")
    text = build_html(film_data(project, data, segs, node_dir, music_version))
    if out is None:
        vdir = versions.next_version(project / "film" / "html")
        out = vdir / FILM_HTML
        out.write_text(text, encoding="utf-8")
        (vdir / MANIFEST).write_text(json.dumps(manifest(project, segs, out.stat().st_size), indent=2) + "\n",
                                     encoding="utf-8")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return out, warnings
