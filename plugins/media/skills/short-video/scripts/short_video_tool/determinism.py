"""Static determinism check of a scene or world page, run by `render` before lint.

HyperFrames seeks the page frame by frame, so the frame at `t` must depend on `t` only. The check reads the
page's inline scripts and styles, its element tags and the author's own local scripts, without running them.
It also refuses a script declaration that shadows a timing helper of timing.js (S, SE, W, WE, ST, STE).
Library files (`LIBS`), kit files (`kit/<file>.js`) and the generated `timing.js` and `card.js` are trusted
and not scanned.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from .js_source import JsSource, blank

# (pattern on code without comments and strings, message)
DETERMINISM = [
    (r"\bsetTimeout\s*\(", "setTimeout: time comes from the timeline only"),
    (r"\bsetInterval\s*\(", "setInterval: time comes from the timeline only"),
    (r"\brequestAnimationFrame\s*\(", "requestAnimationFrame: draw from the timeline's update callback or the "
     "hf-seek listener"),
    (r"\bsetAnimationLoop\s*\(", "setAnimationLoop: draw from the timeline's update callback or the hf-seek "
     "listener"),
    (r"\bTHREE\s*\.\s*Clock\b", "THREE.Clock: time comes from the timeline only"),
    (r"\bDate\s*\.\s*now\s*\(|\bnew\s+Date\b(?!\s*\(\s*[^\s)])",
     "Date.now or new Date() without arguments: a frame must not depend on the wall clock"),
    (r"\bperformance\s*\.\s*now\s*\(", "performance.now: a frame must not depend on the wall clock"),
    (r"\bMath\s*\.\s*random\s*\(", "Math.random: use a seeded generator for repeatable values"),
    (r"\b(anime|utils)\s*\.\s*(random\w*|shuffle)\s*\(|\bd3\s*\.\s*(random\w+|shuffle)\s*\("
     r"|\bMathUtils\s*\.\s*rand\w*\s*\(",
     "library random functions use Math.random: use a seeded generator"),
    (r"\.\s*transition\s*\(", "d3 transitions run on their own timer: animate with the timeline"),
    (r"\brepeat\s*:\s*-\s*1\b|\bloop\s*:\s*(true|-\s*1|Infinity)\b",
     "an endless repeat has no finished state: repeat a fixed number of times"),
    (r"\bautoplay\s*:\s*true\b|\.\s*play\s*\(\s*\)", "HyperFrames owns playback: build the timeline paused"),
    (r"\bnew\s+Audio\b", "the page has no audio: render muxes the narration"),
    (r"\bfetch\s*\(|\bXMLHttpRequest\b|\bimport\s*\(", "the page loads no data at run time: put the data in the "
     "script"),
]
# The timing helpers of timing.js live on `window`; a page declaration of the same name shadows them.
HELPERS = ("S", "SE", "W", "WE", "ST", "STE")
_H = "|".join(HELPERS)
HELPER_DECL = re.compile(rf"\b(?:const|let|var|function|class)\s+({_H})\b|,\s*({_H})\s*=(?![=>])")
CSS_MOTION = re.compile(r"(?<![\w-])(animation|transition)(-[\w-]+)?\s*:|@keyframes", re.I)
JS_STYLE_MOTION = r"\.\s*style\s*\.\s*(animation|transition)\w*"
REMOTE = re.compile(r"^\s*(https?:)?//", re.I)
W3 = re.compile(r"^https?://www\.w3\.org/", re.I)
URL_ATTRS = ("src", "href", "xlink:href", "srcset", "poster")
# Scripts `scaffold` writes from timing.json and the storyboard.
GENERATED = {"timing.js", "card.js"}


def _css_code(text: str) -> str:
    """CSS with comments blanked, newlines kept."""
    out = list(text)
    for m in re.finditer(r"/\*.*?(\*/|$)", text, re.S):
        blank(out, m.start(), m.end())
    return "".join(out)


def check_js(text: str, name: str, first_line: int = 1) -> list[str]:
    """Errors `<name>:<line>: <message>` of a script whose first line is line `first_line` of `name`."""
    src = JsSource(text)
    found: list[tuple[int, str]] = []
    for pattern, msg in DETERMINISM:
        found += [(m.start(), msg) for m in re.finditer(pattern, src.code)]
    for m in HELPER_DECL.finditer(src.code):
        helper = next(g for g in m.groups() if g)
        found.append((m.start(), f"declaration of {helper!r} shadows the timing helper {helper}(): rename it "
                      "(frame size: FW, FH)"))
    for m in re.finditer(JS_STYLE_MOTION, src.code):
        found.append((m.start(), "CSS animation or transition set from the script: tween the property"))
    for s in src.strings:
        if s.template:
            continue
        if REMOTE.match(s.value) and not W3.match(s.value):
            found.append((s.start, f"remote URL {s.value!r}: put the file in the version directory"))
        if CSS_MOTION.search(s.value) or s.value.strip().lower() in ("transition", "animation"):
            found.append((s.start, "CSS animation or transition set from the script: tween the property"))
    return [f"{name}:{first_line + src.line(at) - 1}: {msg}" for at, msg in sorted(found)]


def check_css(text: str, name: str, first_line: int = 1) -> list[str]:
    code = _css_code(text)
    out = []
    for m in CSS_MOTION.finditer(code):
        out.append((m.start(), "CSS animation, transition or @keyframes: animate with the timeline"))
    for m in re.finditer(r"url\(\s*['\"]?\s*(https?:)?//", code, re.I):
        out.append((m.start(), "remote URL in CSS: put the file in the version directory"))
    for m in re.finditer(r"@import", code):
        out.append((m.start(), "@import in CSS: put the rules in the page"))
    return [f"{name}:{first_line + code.count(chr(10), 0, at)}: {msg}" for at, msg in sorted(out)]


class _Page(HTMLParser):
    """Collects inline scripts and styles with their first line, `<script src>` values and tag errors."""

    def __init__(self, name: str) -> None:
        super().__init__(convert_charrefs=False)
        self.name = name
        self.scripts: list[tuple[int, str]] = []
        self.styles: list[tuple[int, str]] = []
        self.sources: list[tuple[int, str]] = []
        self.errors: list[str] = []
        self._open: tuple[str, list] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: v or "" for k, v in attrs}
        line = self.getpos()[0]
        where = f"{self.name}:{line}"
        if tag == "audio":
            self.errors.append(f"{where}: <audio>: the page has no audio; render muxes the narration")
        if tag == "video" and "data-start" not in a:
            self.errors.append(f"{where}: <video> without data-start plays on its own clock; HyperFrames seeks "
                               "a clip with data-start")
        for k in URL_ATTRS:
            v = a.get(k, "")
            if REMOTE.match(v) and not W3.match(v):
                self.errors.append(f"{where}: remote URL {v!r}: put the file in the version directory")
        if CSS_MOTION.search(a.get("style", "")):
            self.errors.append(f"{where}: CSS animation or transition in a style attribute")
        if tag == "script" and a.get("src"):
            self.sources.append((line, a["src"]))
        elif tag in ("script", "style"):
            self._open = (tag, [])

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            if not self._open[1]:
                self._open[1].append(self.getpos()[0])
            self._open[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._open is not None and tag == self._open[0]:
            kind, parts = self._open
            if parts:
                (self.scripts if kind == "script" else self.styles).append((parts[0], "".join(parts[1:])))
            self._open = None


def check(sdir: Path, html: str, libs: set[str] | frozenset[str] = frozenset(), kit: str = "kit",
          name: str = "index.html") -> list[str]:
    """Determinism errors of the page `html` of the version directory `sdir`. `libs` are the library file names
    the page may load unscanned; `kit/<file>.js`, timing.js and card.js are not scanned either. Every other local
    `<script src>` that exists in `sdir` is scanned."""
    page = _Page(name)
    page.feed(html)
    page.close()
    errors = list(page.errors)
    for line, text in page.styles:
        errors += check_css(text, name, line)
    for line, text in page.scripts:
        errors += check_js(text, name, line)
    for line, src in page.sources:
        rel = src.removeprefix("./")
        if REMOTE.match(rel):
            errors.append(f"{name}:{line}: remote script {src!r}: load the library files by bare name")
            continue
        if rel in libs or rel in GENERATED or rel.startswith(kit + "/"):
            continue
        path = sdir / rel
        if path.is_file():
            errors += check_js(path.read_text(encoding="utf-8"), rel)
    return errors
