"""short_video_tool: the HTML film (`html`), the page an HTML scene plays from (`pages`), the arguments of `stills`,
and status of a scene with a page and no render."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from short_video_tool import film_html, pages, scenes, settings, status, stills, storyboard, world
from short_video_tool.film_html import Kind
from short_video_tool.scenes import SceneError

MD = """# Film

Topic: t.

## intro
Brief: A title fades in.
Length: 1

## a
Brief: Wide.
Length: 1
World: city

## b
Brief: Push in.
Length: 1.5
World: city

## outro
Engine: manim
Brief: A graph.

| Narration | On screen |
|---|---|
| The end. | graph |
"""


def _project(tmp: str) -> tuple[Path, Path, dict]:
    project, node_dir = Path(tmp, "p"), Path(tmp, "node")
    project.mkdir()
    (project / storyboard.MD_FILE).write_text(MD, encoding="utf-8")
    (node_dir / scenes.GSAP_REL).parent.mkdir(parents=True)
    (node_dir / scenes.GSAP_REL).write_text("/* gsap */ var x = '</script>';", encoding="utf-8")
    settings.use_project(project)
    return project, node_dir, storyboard.load(project)


def _film(path: Path) -> dict:
    """The FILM object written into film.html."""
    m = re.search(r"const FILM = (.*?);\n", path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))


class TestInline(unittest.TestCase):

    def test_inline_page(self) -> None:
        """film_html.inline_page inlines a local script as text with `</script` escaped, turns a local picture in an
        attribute, a JS string and a CSS url() into data URIs, keeps a remote script and a path outside the
        directory, and puts the scene script before </body>. Guards a film.html that plays from file:// elsewhere."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp, "v1")
            (base / "kit").mkdir(parents=True)
            (base / "kit" / "glow.js").write_text("var s = '</script>';", encoding="utf-8")
            (base / "background.png").write_bytes(b"\x89PNG")
            Path(tmp, "secret.png").write_bytes(b"no")
            html = ('<html><head><script src="kit/glow.js"></script>'
                    '<script src="https://cdn.example.com/x.js"></script>'
                    '<style>#bg { background: url(background.png); }</style></head><body>'
                    '<img src="background.png"><img src="../secret.png">'
                    '<script>loader.load("background.png");</script></body></html>')
            out = film_html.inline_page(base, html, "SCENE();")
            self.assertIn("<script>var s = '<\\/script>';</script>", out)
            self.assertIn('<script src="https://cdn.example.com/x.js"></script>', out)
            uri = "data:image/png;base64,iVBORw=="
            self.assertEqual(out.count(uri), 3, out)
            self.assertIn('src="../secret.png"', out)
            self.assertTrue(out.endswith("<script>SCENE();</script></body></html>"), out)

    def test_unembedded_fonts(self) -> None:
        """film_html.unembedded_fonts names the first family of each font stack, in `font-family` or a `--font...`
        custom property, that no local @font-face file embeds; an embedded family, a generic one, a var() and a
        face whose file is missing are handled. Guards the `html` warning for fonts film.html cannot carry
        (references/scenes.md, Fonts)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "fonts").mkdir()
            (base / "fonts" / "Barlow-Bold.ttf").write_bytes(b"ttf")
            html = ('<style>@font-face { font-family: "Barlow"; src: url("fonts/Barlow-Bold.ttf"); }'
                    '@font-face { font-family: "Gone"; src: url("fonts/Gone.ttf"); }'
                    ':root { --font: "Barlow", sans-serif; --font-num: "Nimbus Sans Narrow", "Barlow", sans-serif; }'
                    'h1 { font-family: var(--font); } p { font-family: Gone, serif; } i { font-family: sans-serif; }'
                    'b { font-family: \'Nimbus Sans Narrow\'; }</style>')
            self.assertEqual(film_html.embedded_families(base, html), {"barlow"})
            self.assertEqual(film_html.unembedded_fonts(base, html), ["Nimbus Sans Narrow", "Gone"])

    def test_script_json_escapes_tags(self) -> None:
        """film_html.script_json escapes every `<`, so no page text closes the player's script. Guards the pages
        embedded in film.html."""
        self.assertEqual(film_html.script_json({"page": "</script><!--"}), '{"page": "\\u003c/script>\\u003c!--"}')


class TestSegments(unittest.TestCase):

    def tearDown(self) -> None:
        settings.use_project(None)

    def test_order_world_and_missing(self) -> None:
        """film_html.segments plays the scenes in storyboard order: a plain page, the world once spanning its two
        scenes at their world starts, and a card for the manim scene with no render. Guards the film's scene
        order and the world playing as one page."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp)
            intro = scenes.scaffold(project, storyboard.scene_by_id(data, "intro"), node_dir)
            wdir = world.scaffold(project, data, "city", node_dir)
            segs, warnings = film_html.segments(project, data)
            self.assertEqual([s.kind for s in segs], [Kind.PAGE, Kind.PAGE, Kind.MISSING])
            self.assertEqual([s.source for s in segs[:2]], [intro, wdir])
            self.assertEqual([[m.id for m in s.scenes] for s in segs], [["intro"], ["a", "b"], ["outro"]])
            self.assertEqual([(m.start, m.duration) for m in segs[1].scenes], [(0.0, 1.0), (1.0, 1.5)])
            self.assertEqual([s.start for s in segs], [0.0, 1.0, 3.5])
            self.assertEqual(segs[2].duration, film_html.MISSING_SECONDS)
            # the scaffolded pages name Inter without embedding it; the manim scene shows a card
            self.assertEqual(len(warnings), 3, warnings)
            self.assertIn("scene intro: font 'Inter' is not embedded", warnings[0])
            self.assertIn("world city: font 'Inter' is not embedded", warnings[1])
            self.assertIn("outro", warnings[2])

    def test_write(self) -> None:
        """film_html.write writes film/html/v1/film.html with the player, each page inlined with its segment
        index and the scene script, no audio for a silent film, and manifest.json. Guards the standalone file."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp)
            scenes.scaffold(project, storyboard.scene_by_id(data, "intro"), node_dir)
            world.scaffold(project, data, "city", node_dir)
            out, _ = film_html.write(project, data, node_dir)
            self.assertEqual(out, project / "film" / "html" / "v1" / "film.html")
            film = _film(out)
            self.assertEqual((film["duration"], film["audio"]), (6.5, []))
            self.assertEqual([s["kind"] for s in film["segments"]], ["page", "page", "missing"])
            for k, seg in enumerate(film["segments"][:2]):
                self.assertIn(f"window.__FILM_INDEX = {k};", seg["page"])
                self.assertIn("/* gsap */", seg["page"])
                self.assertNotIn('src="gsap.min.js"', seg["page"])
                self.assertIn('"film:seeked"', seg["page"])
            self.assertIn('data-composition-id="city"', film["segments"][1]["page"])
            manifest = json.loads((out.parent / film_html.MANIFEST).read_text())
            self.assertEqual([s["source"] for s in manifest["segments"]],
                             ["scenes/intro/v1", "worlds/city/v1", None])

    def test_scene_page(self) -> None:
        """pages.scene_page gives a plain scene's latest page at 0, a world scene's world page at its start, and
        refuses a manim scene and an HTML scene with no page. Guards which page `stills` and `check` open."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp)
            with self.assertRaisesRegex(SceneError, "run `scaffold` first"):
                pages.scene_page(project, data, storyboard.scene_by_id(data, "intro"))
            with self.assertRaisesRegex(SceneError, "manim scene"):
                pages.scene_page(project, data, storyboard.scene_by_id(data, "outro"))
            scenes.scaffold(project, storyboard.scene_by_id(data, "intro"), node_dir)
            wdir = world.scaffold(project, data, "city", node_dir)
            self.assertEqual(pages.scene_page(project, data, storyboard.scene_by_id(data, "intro")),
                             pages.Page(project / "scenes" / "intro" / "v1", 0.0, 1.0))
            self.assertEqual(pages.scene_page(project, data, storyboard.scene_by_id(data, "b")),
                             pages.Page(wdir, 1.0, 1.5, "city"))

    def test_status_of_a_page_without_render(self) -> None:
        """status reports a scaffolded HTML scene and a scaffolded world as current with no render, and a plain
        HTML scene with no page as needing scaffold. Guards status not calling an HTML scene stale for lack of
        a render."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp)
            first = {s["id"]: s for s in status.report(project, data)["scenes"]}
            self.assertEqual(first["intro"]["render_reasons"], ["no page version; run scaffold"])
            self.assertEqual(first["a"]["render_reasons"], ["no world version; run scaffold"])
            scenes.scaffold(project, storyboard.scene_by_id(data, "intro"), node_dir)
            world.scaffold(project, data, "city", node_dir)
            report = {s["id"]: s for s in status.report(project, data)["scenes"]}
            for sid in ("intro", "a", "b"):
                self.assertEqual((report[sid]["needs_render"], report[sid]["rendered"]), (False, False), sid)


class TestStillsArguments(unittest.TestCase):

    def test_mark_and_times(self) -> None:
        """stills.Mark.parse reads a point and a rectangle and refuses other shapes; parse_times reads seconds.
        Guards the `--mark` and `--at` arguments."""
        self.assertEqual(stills.Mark.parse("10,20"), stills.Mark(10, 20))
        self.assertEqual(stills.Mark.parse("10,20,30,40"), stills.Mark(10, 20, 30, 40))
        for bad in ("1", "1,2,3", "1,2,0,4", "a,b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                stills.Mark.parse(bad)
        self.assertIn("w=30:h=40", stills.Mark.parse("10,20,30,40").filter())
        self.assertIn("t=fill", stills.Mark(10, 20).filter())
        self.assertEqual(stills.parse_times("1.2, 3.4"), [1.2, 3.4])
        with self.assertRaises(ValueError):
            stills.parse_times("soon")

    def test_time_outside_scene(self) -> None:
        """stills.stills refuses a time outside the scene before it starts the browser. Guards a still of a
        neighbouring scene of a world."""
        page = pages.Page(Path("/nonexistent"), 1.0, 1.5, "city")
        with self.assertRaisesRegex(SceneError, "outside scene b"):
            stills.stills("b", page, [1.5], Path("/nonexistent"))

    def test_sheet_filter(self) -> None:
        """stills.sheet_filter scales and labels each still and tiles them at most `columns` wide. Guards the
        contact sheet layout."""
        f = stills.sheet_filter(["a 0.50 s", "a 1.00 s", "a 1.50 s"], 480, 2)
        self.assertIn("[0:v]scale=480:-2,drawtext=text='a 0.50 s'", f)
        self.assertTrue(f.endswith("[s0][s1][s2]concat=n=3:v=1:a=0,tile=2x2"), f)


if __name__ == "__main__":
    unittest.main()
