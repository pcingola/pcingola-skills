"""`validate`: static checks of an animation folder. They need no browser."""
from __future__ import annotations

import hashlib
import json
import re

from .animation import Animation
from .builder import Builder
from .chapter_html import ChapterHtml
from .common import PLAYER, HAError
from .enums import Rule, TimingLib
from .issue import Issue
from .js_source import JsSource
from .lib_pin import PINS
from .project import Project
from .report import Report

# (pattern on code without comments and strings, message)
DETERMINISM = [
    (r"\bsetTimeout\s*\(", "setTimeout: time comes from the timeline only"),
    (r"\bsetInterval\s*\(", "setInterval: time comes from the timeline only"),
    (r"\brequestAnimationFrame\s*\(", "requestAnimationFrame: render inside the timeline's update callback"),
    (r"\bsetAnimationLoop\s*\(", "setAnimationLoop: render inside the timeline's update callback"),
    (r"\bTHREE\s*\.\s*Clock\b", "THREE.Clock: time comes from the timeline only"),
    (r"\bDate\s*\.\s*now\s*\(|\bnew\s+Date\b", "Date: a frame must not depend on the wall clock"),
    (r"\bperformance\s*\.\s*now\s*\(", "performance.now: a frame must not depend on the wall clock"),
    (r"\bMath\s*\.\s*random\s*\(", "Math.random: use HA.random(seed) for repeatable values"),
    (r"\b(anime|utils)\s*\.\s*(random\w*|shuffle)\s*\(|\bd3\s*\.\s*(random\w+|shuffle)\s*\(|\bMathUtils\s*\.\s*rand\w*\s*\(",
     "library random functions use Math.random: use HA.random(seed)"),
    (r"\.\s*transition\s*\(", "d3 transitions run on their own timer: animate with the timeline"),
    (r"\brepeat\s*:\s*-\s*1\b|\bloop\s*:\s*(true|-\s*1|Infinity)\b",
     "an endless repeat has no finished state: repeat a fixed number of times"),
    (r"\bautoplay\s*:\s*true\b|\.\s*play\s*\(\s*\)", "the player owns playback: build the timeline paused"),
    (r"\bnew\s+Audio\b", "audio does not seek with the timeline"),
]
OFFLINE = [
    (r"\bfetch\s*\(|\bXMLHttpRequest\b|\bimport\s*\(", "index.html plays from file://: read data from content.json"),
]
QUERY = r"\.\s*(querySelector(All)?|getElementsBy\w+)\s*\("
CSS_MOTION = re.compile(r"(?<![\w-])(animation|transition)(-[\w-]+)?\s*:|@keyframes", re.I)
JS_STYLE_MOTION = r"\.\s*style\s*\.\s*(animation|transition)\w*"
REMOTE = re.compile(r"^\s*(https?:)?//", re.I)
W3 = re.compile(r"^https?://www\.w3\.org/", re.I)
ID_LITERAL = re.compile(r"^#([A-Za-z][\w-]*)$")
TAG = re.compile(r"^[a-z][a-z0-9-]*$")
NO_ID_TAGS = {"style", "br", "wbr"}
RESERVED_ID = re.compile(r"^(ch-|ha-)")
# Calls whose first argument is a target: a selector string must be "#<id>".
SELECTOR_CALLS = r"(\.\s*(to|from|fromTo|set)|\banimate|\bd3\s*\.\s*select(All)?|\butils\s*\.\s*\$)\s*\("
ID_CALLS = r"(\bel|\bgetElementById)\s*\("
CREATE_CALLS = r"\bcreateElement(NS)?\s*\(|\bnew\s+THREE\s*\.\s*WebGLRenderer\b"
TIMING_GLOBALS = {TimingLib.GSAP: "gsap", TimingLib.ANIME: "anime", TimingLib.MOTION: "Motion"}


class Validator:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.report = Report()

    def add(self, file: str, line: int | None, rule: Rule, message: str) -> None:
        self.report.errors.append(Issue(file, line, rule, message))

    def run(self) -> Report:
        p = self.project
        if not p.animation_json.is_file():
            self.add("animation.json", None, Rule.FORMAT, "animation.json not found; run init")
            return self.report
        try:
            data = json.loads(p.animation_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            self.add("animation.json", e.lineno, Rule.FORMAT, f"not valid JSON: {e.msg}")
            return self.report
        problems = Animation.problems(data)
        for msg in problems:
            self.add("animation.json", None, Rule.FORMAT, msg)
        if problems:
            return self.report
        animation = Animation.from_dict(data)
        if not animation.chapters:
            self.add("animation.json", None, Rule.FORMAT, "no chapters; add one with add-chapter")
        content = self._content()
        self._files(animation)
        htmls = self._htmls(animation)
        scripts = self._scripts(animation, htmls, content)
        if content is not None:
            self._content_used(content, scripts)
        if not self.report.errors:
            self._build()
        return self.report

    # animation folder files

    def _content(self) -> dict | None:
        p = self.project
        if not p.content_json.is_file():
            self.add("content.json", None, Rule.FORMAT, "content.json not found")
            return None
        try:
            data = json.loads(p.content_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            self.add("content.json", e.lineno, Rule.FORMAT, f"not valid JSON: {e.msg}")
            return None
        if not isinstance(data, dict):
            self.add("content.json", None, Rule.FORMAT, "content.json must be an object")
            return None
        return data

    def _files(self, animation: Animation) -> None:
        p = self.project
        if not p.player_js.is_file():
            self.add("player.js", None, Rule.FORMAT, "player.js not found; run init")
        elif p.player_js.read_bytes() != PLAYER.read_bytes():
            self.add("player.js", None, Rule.FORMAT, "player.js differs from the skill's player; run init again")
        for key in p.libs():
            pin = PINS[key]
            if hashlib.sha256((p.lib_dir / pin.file).read_bytes()).hexdigest() != pin.sha256:
                self.add(f"lib/{pin.file}", None, Rule.FORMAT, f"differs from the pinned {pin.package}@{pin.version}")
        if animation.lib.value not in p.libs():
            self.add("lib", None, Rule.FORMAT, f"lib/{PINS[animation.lib.value].file} not found; run init --lib "
                     f"{animation.lib.value}")
        known = {c.id for c in animation.chapters}
        if p.chapters_dir.is_dir():
            for f in sorted(p.chapters_dir.iterdir()):
                if f.suffix in (".html", ".js") and f.stem not in known:
                    self.add(f"chapters/{f.name}", None, Rule.FORMAT, f"chapter {f.stem!r} is not in animation.json")
        for c in animation.chapters:
            for path in (p.chapter_html(c.id), p.chapter_js(c.id)):
                if not path.is_file():
                    self.add(f"chapters/{path.name}", None, Rule.FORMAT, "file not found")

    def _build(self) -> None:
        try:
            current = Builder(self.project).current()
        except HAError as e:
            self.add("index.html", None, Rule.BUILD, str(e))
            return
        if not current:
            self.add("index.html", None, Rule.BUILD, "index.html is missing or older than its sources; run build")

    # chapter html

    def _htmls(self, animation: Animation) -> dict[str, ChapterHtml]:
        out: dict[str, ChapterHtml] = {}
        owner: dict[str, str] = {}
        for c in animation.chapters:
            path = self.project.chapter_html(c.id)
            if not path.is_file():
                continue
            name = f"chapters/{path.name}"
            doc = ChapterHtml(path.read_text(encoding="utf-8"))
            out[c.id] = doc
            for e in doc.elements:
                eid = e.attrs.get("id", "")
                if e.tag == "script":
                    self.add(name, e.line, Rule.FORMAT, f"<script> in a chapter html: code goes in chapters/{c.id}.js")
                if e.tag in ("video", "audio"):
                    self.add(name, e.line, Rule.DETERMINISM, f"<{e.tag}> plays on its own clock, not the timeline")
                if e.tag not in NO_ID_TAGS and not eid:
                    self.add(name, e.line, Rule.ID, f"<{e.tag}> has no id")
                if eid and RESERVED_ID.match(eid):
                    self.add(name, e.line, Rule.ID, f"id {eid!r}: the prefixes ch- and ha- belong to the player")
                if eid and eid in owner:
                    where = "this chapter" if owner[eid] == c.id else f"chapters/{owner[eid]}.html"
                    self.add(name, e.line, Rule.ID, f"id {eid!r} is also used in {where}")
                elif eid:
                    owner[eid] = c.id
                style = e.attrs.get("style", "")
                if CSS_MOTION.search(style):
                    self.add(name, e.line, Rule.CSS_MOTION, "CSS animation or transition in a style attribute")
                for k, v in e.attrs.items():
                    if k in ("src", "href", "xlink:href", "srcset", "poster") and REMOTE.match(v) and not W3.match(v):
                        self.add(name, e.line, Rule.OFFLINE, f"remote URL {v!r}: put the file in the folder")
            for s in doc.styles:
                for m in CSS_MOTION.finditer(s.text):
                    line = s.line + s.text.count("\n", 0, m.start())
                    self.add(name, line, Rule.CSS_MOTION, "CSS animation, transition or @keyframes: animate with the timeline")
                for m in re.finditer(r"url\(\s*['\"]?\s*(https?:)?//", s.text, re.I):
                    self.add(name, s.line + s.text.count("\n", 0, m.start()), Rule.OFFLINE,
                             "remote URL in CSS: put the file in the folder")
                for m in re.finditer(r"@import", s.text):
                    self.add(name, s.line + s.text.count("\n", 0, m.start()), Rule.OFFLINE, "@import in CSS")
        return out

    # chapter scripts

    def _scripts(self, animation: Animation, htmls: dict[str, ChapterHtml], content: dict | None) -> list[JsSource]:
        p = self.project
        libs = set(p.libs())
        out = []
        for c in animation.chapters:
            path = p.chapter_js(c.id)
            if not path.is_file():
                continue
            name = f"chapters/{path.name}"
            src = JsSource(path.read_text(encoding="utf-8"))
            out.append(src)
            ids = set(htmls[c.id].ids) if c.id in htmls else set()

            calls = src.calls(r"\bHA\s*\.\s*chapter\s*\(")
            if len(calls) != 1:
                self.add(name, None, Rule.CHAPTER, f"{len(calls)} HA.chapter(...) calls; a chapter script has one")
            for at, arg in calls:
                if arg is None or arg.value != c.id:
                    self.add(name, src.line(at), Rule.CHAPTER, f'the call must be HA.chapter("{c.id}", function (ctx) {{ ... }})')

            for pattern, msg in DETERMINISM:
                for m in re.finditer(pattern, src.code):
                    self.add(name, src.line(m.start()), Rule.DETERMINISM, msg)
            for pattern, msg in OFFLINE:
                for m in re.finditer(pattern, src.code):
                    self.add(name, src.line(m.start()), Rule.OFFLINE, msg)
            for s in src.strings:
                if REMOTE.match(s.value) and not W3.match(s.value) and not s.template:
                    self.add(name, src.line(s.start), Rule.OFFLINE, f"remote URL {s.value!r}: put the file in the folder")
                if CSS_MOTION.search(s.value) or s.value.strip().lower() in ("transition", "animation"):
                    self.add(name, src.line(s.start), Rule.CSS_MOTION, "CSS animation or transition set from the script")
            for m in re.finditer(JS_STYLE_MOTION, src.code):
                self.add(name, src.line(m.start()), Rule.CSS_MOTION, "CSS animation or transition set from the script")

            self._targets(name, src, ids)
            self._libs(name, src, animation, libs)
            if content is not None:
                for m in re.finditer(r"\bcontent\s*\.\s*([A-Za-z_$][\w$]*)", src.code):
                    if m.group(1) not in content:
                        self.add(name, src.line(m.start()), Rule.CONTENT, f"content.{m.group(1)} is not in content.json")
        return out

    def _targets(self, name: str, src: JsSource, ids: set[str]) -> None:
        assigns = self._assigns_ids(src)
        prefixes = [s.value for s in src.strings if s.value and not s.template] if assigns else []

        def known(eid: str) -> bool:
            return eid in ids or any(eid.startswith(pre) for pre in prefixes)

        for m in re.finditer(QUERY, src.code):
            self.add(name, src.line(m.start()), Rule.TARGET, f"{m.group(1)}: reach elements with el(id)")
        for at, arg in src.calls(ID_CALLS):
            if arg is not None and not arg.template and not known(arg.value):
                self.add(name, src.line(at), Rule.TARGET, f"no element with id {arg.value!r} in this chapter")
        for at, arg in src.calls(SELECTOR_CALLS):
            if arg is not None and not arg.template:
                self._selector(name, src.line(at), arg.value, known)
        for at, arg in src.calls(r"\.\s*add\s*\("):
            if arg is not None and not arg.template and re.match(r"^[#.\[]|.*[\s>\[]", arg.value):
                self._selector(name, src.line(at), arg.value, known)
        # Motion sequence segments: [".selector", {...}, ...]
        for s in src.strings:
            before = src.code[:s.start].rstrip()
            after = src.code[s.start + len(s.value) + 2:].lstrip()
            if before.endswith("[") and after.startswith(",") and after[1:].lstrip().startswith("{") and not s.template:
                self._selector(name, src.line(s.start), s.value, known)
        creates = [at for at, arg in src.calls(r"\.\s*(append|insert|join)\s*\(")
                   if arg is not None and TAG.match(arg.value)]
        creates += [m.start() for m in re.finditer(CREATE_CALLS, src.code)]
        if creates and not assigns:
            self.add(name, src.line(creates[0]), Rule.TARGET,
                     "the script creates elements but gives none an id: set .attr(\"id\", ...) or .id")

    def _selector(self, name: str, line: int, value: str, known) -> None:
        m = ID_LITERAL.match(value.strip())
        if not m:
            self.add(name, line, Rule.TARGET, f"target {value!r}: reach elements with el(id) or \"#<id>\"")
        elif not known(m.group(1)):
            self.add(name, line, Rule.TARGET, f"no element with id {m.group(1)!r} in this chapter")

    @staticmethod
    def _assigns_ids(src: JsSource) -> bool:
        if re.search(r"\.\s*id\s*=(?!=)", src.code):
            return True
        for at, arg in src.calls(r"\b(attr|setAttribute)\s*\("):
            if arg is not None and arg.value == "id":
                return True
        return False

    def _libs(self, name: str, src: JsSource, animation: Animation, libs: set[str]) -> None:
        for key, glob in (("d3", "d3"), ("three", "THREE")):
            m = re.search(rf"\b{glob}\s*\.", src.code)
            if m and key not in libs:
                self.add(name, src.line(m.start()), Rule.LIB, f"{glob} is used but lib/{PINS[key].file} is missing; "
                         f"run init --lib {animation.lib.value} --with {key}")
        for lib, glob in TIMING_GLOBALS.items():
            m = re.search(rf"(?<![\w$.]){glob}\s*\.", src.code)
            if m and lib != animation.lib:
                self.add(name, src.line(m.start()), Rule.LIB, f"{glob} is not this animation's timing library "
                         f"({animation.lib.value})")

    def _content_used(self, content: dict, scripts: list[JsSource]) -> None:
        for key in content:
            word = re.compile(rf"(?<![\w$]){re.escape(key)}(?![\w$])")
            used = any(word.search(s.code) or any(st.value == key for st in s.strings) for s in scripts)
            if not used:
                self.add("content.json", self._key_line(key), Rule.CONTENT, f"key {key!r} is used by no chapter")

    def _key_line(self, key: str) -> int | None:
        text = self.project.content_json.read_text(encoding="utf-8")
        i = text.find(json.dumps(key))
        return text.count("\n", 0, i) + 1 if i >= 0 else None
