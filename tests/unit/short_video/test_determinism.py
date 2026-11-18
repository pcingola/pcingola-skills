"""determinism.check: each rule fails with its file and line; the same words in comments and strings, library,
kit and generated files, and every page under assets/ pass."""
import tempfile
import unittest
from pathlib import Path

from short_video_tool import determinism, settings
from short_video_tool.scenes import KIT, LIBS

HEAD = """<!doctype html>
<html>
<head>
<script src="gsap.min.js"></script>
<script src="timing.js"></script>
</head>
<body>
<div id="root" data-composition-id="s1" data-start="0" data-duration="4"></div>
<script>
const tl = gsap.timeline({ paused: true });
"""  # the body starts at line 8; the script body at line 11
TAIL = """window.__timelines["s1"] = tl;
</script>
</body>
</html>
"""


def page(body: str) -> str:
    return HEAD + body + "\n" + TAIL


class TestDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def check(self, html: str) -> list[str]:
        return determinism.check(self.dir, html, set(LIBS), KIT)

    def test_script_rules(self) -> None:
        """determinism.check fails timers, clocks, Math.random, library random functions, d3 transitions, endless
        repeats, self playing timelines, audio and run-time loading at their line. Guards render refusing a page
        whose frames depend on wall time."""
        bad = [
            "setTimeout(function () {}, 10);",
            "setInterval(function () {}, 10);",
            "requestAnimationFrame(draw);",
            "renderer.setAnimationLoop(draw);",
            "const clock = new THREE.Clock();",
            "const now = Date.now();",
            "const d = new Date();",
            "const p = performance.now();",
            "const r = Math.random();",
            "const r = d3.randomUniform(0, 1)();",
            "const r = anime.utils.random(0, 9);",
            "const r = THREE.MathUtils.randFloat(0, 1);",
            "d3.select('#bar').transition().duration(5);",
            "tl.to('#box', { x: 10, repeat: -1 });",
            "const a = anime.createTimeline({ loop: true });",
            "const a = anime.createTimeline({ autoplay: true });",
            "tl.play();",
            "const s = new Audio('a.mp3');",
            "fetch('data.json');",
            "document.getElementById('box').style.transition = 'all 1s';",
            "tl.set('#box', { css: 'transition: opacity 1s' });",
        ]
        for line in bad:
            with self.subTest(line):
                errors = self.check(page(line))
                self.assertTrue(errors, line)
                self.assertTrue(all(e.startswith("index.html:11: ") for e in errors), errors)

    def test_comments_and_strings_pass(self) -> None:
        """determinism.check passes forbidden words inside JS comments and strings, a finite GSAP repeat and a
        helper call whose word is "random". Guards false refusals of a page that only names a rule."""
        ok = page('// setTimeout and Math.random() in a comment\n/* new Date() */\nconst s = "setInterval(";\n'
                  'tl.to("#box", { opacity: 1, yoyo: true, repeat: 3 }, W(1, "random"));')
        self.assertEqual(self.check(ok), [])

    def test_literal_dates_pass(self) -> None:
        """determinism.check passes new Date with arguments (literal dates for d3.scaleTime) passes; new Date without arguments, Date.now
        and performance.now fail. Guards the wall-clock rule against refusing fixed dates."""
        ok = page('const x = d3.scaleTime().domain([new Date(2020, 0, 1), new Date("2024-06-30")]);\n'
                  "const t = new Date(ms);")
        self.assertEqual(self.check(ok), [])
        for line in ("const d = new Date;", "const d = new Date( );", "const d = Date.now();",
                     "const p = performance.now();"):
            with self.subTest(line):
                self.assertTrue(self.check(page(line)), line)

    def test_helper_names_not_declared(self) -> None:
        """A declaration of a timing helper name (S, SE, W, WE, ST, STE) fails at its line, including the second
        name of a declaration list; other names and helper calls pass. Guards `const W = 1920` shadowing W()."""
        bad = ["const W = 1920, H = 1080;", "const D = 7, W = 1920;", "let S = 0;", "var STE = 2;",
               "function WE() {}"]
        for line in bad:
            with self.subTest(line):
                errors = self.check(page(line))
                self.assertTrue(errors and all(e.startswith("index.html:11: ") for e in errors), errors)
                self.assertIn("shadows the timing helper", errors[0])
        ok = page('const FW = 1920, FH = 1080, Wide = 2;\ntl.to("#a", { x: 1 }, W(1, "x"));\n'
                  "const same = FW == W;")
        self.assertEqual(self.check(ok), [])

    def test_css_and_tags(self) -> None:
        """determinism.check fails CSS motion in a style block or attribute, remote URLs, <audio> and a <video>
        without data-start at their line, and passes a CSS comment and a seekable clip."""
        html = page("").replace("</head>", "<style>\n#a { transition: opacity 1s; }\n@keyframes spin { }\n"
                                "/* animation: none; */\n#b { background: url(https://example.com/a.png); }\n"
                                "</style>\n</head>")
        errors = self.check(html)
        self.assertEqual([e.split(": ")[0] for e in errors], ["index.html:7", "index.html:8", "index.html:10"])
        tags = page("").replace('<div id="root"', '<audio src="a.mp3"></audio>\n<video src="v.mp4"></video>\n'
                                '<video src="b.mp4" data-start="0" muted></video>\n'
                                '<img src="//cdn.example.com/x.png">\n<p style="animation: x 1s"></p>\n<div id="root"')
        self.assertEqual([e.split(": ")[0] for e in self.check(tags)],
                         ["index.html:8", "index.html:9", "index.html:11", "index.html:12"])
        svg = page('const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");')
        self.assertEqual(self.check(svg), [])

    def test_script_files(self) -> None:
        """determinism.check scans the author's own script file; it skips library, kit, timing.js and card.js
        files by name and reports a remote script."""
        for rel in ("gsap.min.js", "timing.js", "card.js", "kit/camera.js", "mine.js"):
            (self.dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.dir / rel).write_text("var r = Math.random();\n")
        srcs = "".join(f'<script src="{s}"></script>\n' for s in ("card.js", "kit/camera.js", "./mine.js"))
        errors = self.check(page("").replace("</head>", srcs + "</head>"))
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("mine.js:1: Math.random"), errors)
        remote = page("").replace("</head>", '<script src="https://cdn.example.com/gsap.js"></script>\n</head>')
        self.assertTrue(any("remote script" in e for e in self.check(remote)))

    def test_asset_pages_pass(self) -> None:
        """determinism.check passes the suggested pages, the world page and every technique page in assets/.
        Guards render refusing a page the skill ships."""
        assets = settings.ASSETS_DIR
        pages = sorted(p for p in assets.glob("*.html") if p.name != "film-player.html")  # the film player owns a clock
        pages += sorted(assets.glob("techniques/*/index.html"))
        self.assertTrue(pages)
        for p in pages:
            with self.subTest(str(p.relative_to(assets))):
                self.assertEqual(determinism.check(p.parent, p.read_text(encoding="utf-8"), set(LIBS), KIT), [])
