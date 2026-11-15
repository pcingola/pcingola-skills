"""validate: a valid folder passes; each rule fails on a source that breaks it."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from html_animation_tool.builder import Builder
from html_animation_tool.project import Project
from html_animation_tool.validator import Validator

from tests.unit.html_animation.fixture import DATA, box_project

GSAP_JS = (DATA / "gsap.js").read_text()
BOX_HTML = (DATA / "box.html").read_text()


def script(body: str) -> str:
    """A gsap chapter script for `box` with `body` before the return."""
    return ('HA.chapter("box", function (ctx) {\n  var el = ctx.el, content = ctx.content;\n'
            '  el("box-label").textContent = content.label;\n  el("box-block").style.background = content.color;\n'
            '  var tl = gsap.timeline({ paused: true });\n' + body + '\n  return tl;\n});\n')


class TestValidate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.p = box_project(Path(self._tmp.name) / "a")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def check(self, js: str | None = None, html: str | None = None, content: dict | None = None) -> list[tuple]:
        """Write the given sources, build when possible, validate; return (rule, file, line) of each error."""
        if js is not None:
            self.p.chapter_js("box").write_text(js)
        if html is not None:
            self.p.chapter_html("box").write_text(html)
        if content is not None:
            self.p.content_json.write_text(json.dumps(content))
        Builder(self.p).build()
        report = Validator(self.p).run()
        return [(e.rule.value, e.file, e.line) for e in report.errors]

    def rules(self, **kw) -> set[str]:
        return {r for r, _, _ in self.check(**kw)}

    def test_valid_folder(self) -> None:
        """The test folder validates on every timing library."""
        self.assertEqual(self.check(), [])
        for lib in ("anime", "motion"):
            with self.subTest(lib):
                p = box_project(Path(self._tmp.name) / lib, lib)
                self.assertEqual(Validator(p).run().to_dict(), {"ok": True, "errors": []})

    def test_stale_build(self) -> None:
        """A source changed after build fails the build rule."""
        self.p.chapter_js("box").write_text(GSAP_JS + "\n")
        report = Validator(self.p).run()
        self.assertEqual([e.rule.value for e in report.errors], ["build"])

    def test_determinism(self) -> None:
        """Timers, clocks, Math.random, library random functions, d3 transitions, endless repeats and self
        playing timelines fail with their line; the same words in a comment or a string pass."""
        bad = {
            "setTimeout(function () {}, 10);": 6,
            "setInterval(function () {}, 10);": 6,
            "requestAnimationFrame(function () {});": 6,
            "var now = Date.now();": 6,
            "var d = new Date();": 6,
            "var p = performance.now();": 6,
            "var r = Math.random();": 6,
            "var r = d3.randomUniform(0, 1)();": 6,
            "d3.select(el('box-block')).transition().duration(5);": 6,
            "tl.to(el('box-block'), { x: 10, repeat: -1 });": 6,
            "tl.play();": 6,
        }
        for line, at in bad.items():
            with self.subTest(line):
                self.assertIn(("determinism", "chapters/box.js", at), self.check(js=script("  " + line)))
        ok = script('  // setTimeout and Math.random() in a comment\n  var s = "setInterval(";\n  var r = HA.random(3)();')
        self.assertEqual(self.check(js=ok), [])

    def test_css_motion(self) -> None:
        """CSS transitions, animations and @keyframes fail in a style block, a style attribute and a script."""
        html = BOX_HTML.replace('<div id="box-bg"', '<style>\n#box-tag { transition: opacity 1s; }\n'
                                '@keyframes spin { from { opacity: 0; } }\n</style>\n<div id="box-bg"')
        errors = self.check(html=html)
        self.assertIn(("css-motion", "chapters/box.html", 2), errors)
        self.assertIn(("css-motion", "chapters/box.html", 3), errors)
        self.assertIn("css-motion", self.rules(html=BOX_HTML.replace("margin: 0;", "margin: 0; animation: x 1s;")))
        self.assertIn("css-motion", self.rules(html=BOX_HTML, js=script('  el("box-tag").style.transition = "all 1s";')))
        self.assertIn("css-motion", self.rules(js=script('  d3.select(el("box-tag")).style("transition", "x");')))

    def test_ids(self) -> None:
        """Every element of a chapter html has an id; reserved prefixes and duplicates fail."""
        self.assertIn(("id", "chapters/box.html", 2), self.check(html=BOX_HTML.replace(' id="box-block"', "")))
        self.assertIn("id", self.rules(html=BOX_HTML.replace('id="box-tag"', 'id="ch-tag"')))
        self.assertIn("id", self.rules(html=BOX_HTML.replace('id="box-tag"', 'id="box-label"')))
        self.assertEqual(self.check(html=BOX_HTML.replace("Seek", "") + "<style>#box-bg { color: red; }</style><br>"),
                         [])

    def test_targets(self) -> None:
        """Scripts reach elements by id: queries, class selectors, unknown ids and created elements without
        ids fail; "#id" of an existing element, colour strings and d3 joins that set ids pass."""
        cases = {
            'el("box-nope").style.color = "red";': True,
            'tl.from(".box", { opacity: 0 });': True,
            'tl.from("#box-nope", { opacity: 0 });': True,
            'ctx.root.querySelector("p").textContent = "x";': True,
            'd3.select("svg");': True,
            'd3.select(el("box-bg")).append("div");': True,
            'tl.from("#box-tag", { opacity: 0, color: "#ffffff" });': False,
            'd3.select(el("box-bg")).selectAll("i").data([1, 2]).join("i").attr("id", function (d) { return "box-i" + d; });\n'
            '  tl.from(el("box-i1"), { opacity: 0 });': False,
            'tl.add("intro", 0.5);': False,
        }
        for body, fails in cases.items():
            with self.subTest(body):
                self.assertEqual("target" in self.rules(js=script("  " + body)), fails)

    def test_content(self) -> None:
        """An unused content key fails at its line in content.json; content.<key> missing from content.json fails."""
        errors = self.check(content={"label": "x", "color": "#000", "unused": 1})
        self.assertEqual(errors, [("content", "content.json", 1)])
        self.assertIn(("content", "chapters/box.js", 6), self.check(js=script("  var t = content.title;")))

    def test_offline(self) -> None:
        """Remote URLs and fetch fail; SVG namespaces pass."""
        self.assertIn("offline", self.rules(html=BOX_HTML + '<img id="box-img" src="https://example.com/a.png">'))
        self.assertIn("offline", self.rules(js=script('  fetch("data.json");')))
        ns = script('  var s = document.createElementNS("http://www.w3.org/2000/svg", "svg");\n  s.id = "box-svg";')
        self.assertEqual(self.check(js=ns, html=BOX_HTML), [])

    def test_libs_and_chapter_call(self) -> None:
        """d3 without lib/d3.min.js, another timing library's global and a wrong HA.chapter id fail."""
        self.assertIn("lib", self.rules(js=script("  var x = d3.scaleLinear();")))
        self.assertIn("lib", self.rules(js=script("  anime.createTimeline({ autoplay: false });")))
        self.assertIn("chapter", self.rules(js=GSAP_JS.replace('HA.chapter("box"', 'HA.chapter("other"')))

    def test_format(self) -> None:
        """A modified player.js, an orphan chapter file and a broken animation.json fail the format rule."""
        self.p.player_js.write_text("// changed")
        self.p.chapter_js("box").with_name("old.js").write_text("")
        errors = self.check()
        self.assertIn(("format", "player.js", None), errors)
        self.assertIn(("format", "chapters/old.js", None), errors)
        self.p.animation_json.write_text('{"title": ""}')
        report = Validator(self.p).run()
        self.assertFalse(report.ok)
        self.assertEqual(report.rules(), {"format"})

    def test_missing_folder(self) -> None:
        report = Validator(Project(Path(self._tmp.name) / "none")).run()
        self.assertEqual([e.rule.value for e in report.errors], ["format"])
