"""short_video_tool.manim_scene and the `Engine:` storyboard key: parsing,
the `sv_timing.py` header, the helper check on
Python source, the starting page and the scaffold of a manim scene."""
import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.subproc import child_env, py_value, run_python
from short_video_tool import cli, config, manim_scene, scenes, settings, state, storyboard, versions

MD = """\
# Manim

Topic: Plots.

## plot
Engine: manim
Brief: Draw the curve.

| Narration | On screen |
|---|---|
| The curve rises. | curve drawn on "rises" |

## photo
Engine: manim
Image: a.png
Brief: Zoom in.

| Narration | On screen |
|---|---|
| Look closer. | zoom |

## html
Engine: html
Image: a.png
Brief: Pan.

| Narration | On screen |
|---|---|
| Then pan. | pan |

## plain
Image: a.png
Brief: Hold.

| Narration | On screen |
|---|---|
| Hold still. | hold |
"""


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


class TestEngineKey(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads `Engine: manim` with and without Image, `Engine: html`, and no Engine
        key, and manim_scene.is_manim tells them apart. Guards Image being optional for manim scenes only."""
        plot, photo, html, plain = storyboard.parse_markdown(MD)["scenes"]
        self.assertEqual(plot, {"id": "plot", "brief": "Draw the curve.", "engine": "manim",
                                "narration": ["The curve rises."], "beats": ['curve drawn on "rises"']})
        self.assertEqual(photo["image"], "a.png")
        self.assertEqual(photo["engine"], "manim")
        self.assertEqual(html, {"id": "html", "image": "a.png", "brief": "Pan.", "engine": "html",
                                "narration": ["Then pan."], "beats": ["pan"]})
        self.assertEqual(plain, {"id": "plain", "image": "a.png", "brief": "Hold.",
                                 "narration": ["Hold still."], "beats": ["hold"]})
        self.assertTrue(manim_scene.is_manim(plot))
        self.assertFalse(manim_scene.is_manim(html) or manim_scene.is_manim(plain))

    def test_errors(self) -> None:
        """storyboard.parse_markdown refuses an unknown or empty engine, a manim scene without Brief, Engine on
        a template and an html scene without Brief, each with its line. Guards the Engine key rules."""
        cases = [  # (replace, with, line, fragment)
            ("Engine: html", "Engine: blender", 23, "`Engine:` must be one of html, manim"),
            ("Engine: html", "Engine:", 23, "`Engine:` must be one of"),
            ("Brief: Draw the curve.\n", "", 5, "scene 'plot': missing `Brief:`"),
            ("Engine: manim\nBrief: Draw the curve.", "Engine: manim\nTemplate: title", 6,
             "a template scene takes no `Engine:`"),
            ("Engine: html\nImage: a.png\nBrief: Pan.\n", "Engine: html\n", 22, "scene 'html': missing `Brief:`"),
        ]
        for old, new, line, fragment in cases:
            with self.subTest(fragment=fragment):
                msg = _error(MD.replace(old, new, 1))
                prefix = f"storyboard.md line {line}: "
                self.assertTrue(any(m.startswith(prefix) and fragment in m for m in msg.splitlines()), msg)

    def test_validate_without_image(self) -> None:
        """storyboard.validate gives no error or warning for a manim scene without an image. Guards the image
        checks skipping manim scenes."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "images").mkdir()
            (project / "images" / "a.png").write_bytes(b"")
            (project / "settings.yaml").write_text("author: [Jane Doe]\nlength: {min_seconds: 1}\n")
            (project / "storyboard.md").write_text(MD)
            settings.use_project(project)
            try:
                r = storyboard.validate(storyboard.parse_markdown(MD), project)
            finally:
                settings.use_project(None)
            self.assertEqual(r.errors, [])
            self.assertFalse(any("scene plot" in w for w in r.warnings), r.warnings)


def _sentence(i: int, text: str, start: float) -> dict:
    words = [{"text": w, "start": start + k * 0.3, "end": start + k * 0.3 + 0.25} for k, w in enumerate(text.split())]
    return {"index": i, "text": text, "start": start, "end": words[-1]["end"], "words": words, "aligned": True}


TIMING = {"duration": 4.5667, "backend": "kokoro", "sentences": [
    _sentence(1, "A virus enters the cell.", 0.37),
    _sentence(2, "The cell copies the virus, virus after Virus.", 2.111),
]}


class TestSvTiming(unittest.TestCase):

    def test_header(self) -> None:
        """manim_scene.sv_timing_py writes a generated-file header naming the timing source. Guards the generated
        module's provenance line."""
        text = manim_scene.sv_timing_py(TIMING, "voice/x/v1/timing.json")
        self.assertTrue(text.startswith(
            "# Generated by short-video scaffold from voice/x/v1/timing.json. Do not edit.\n"))


class TestStaticCheckAndPage(unittest.TestCase):

    def test_check_helpers_on_python(self) -> None:
        """manim_scene.check_scene_py checks literal helper calls in scene.py, keyword k= included, ignores non-
        literal ones and reports errors with the line. Guards render's static check of manim scenes."""
        ok = ('self.at(S(1))\nself.at(SE(2) - fade)\nself.at(W(1, "virus"))\nself.at(WE(2, \'virus\', 3))\n'
              'self.at(W(2, "virus", k=2))\nself.at(W(n, word))\nself.at(S(n))\nlabel.S(9)\n')
        self.assertEqual(manim_scene.check_scene_py(ok, TIMING), ([], 5))
        for call, fragment in [('W(1, "bacteria")', "not found"), ('W(2, "virus", k=4)', "3 occurrence"),
                               ("S(3)", "no sentence")]:
            with self.subTest(call=call):
                errors, _ = manim_scene.check_scene_py("x = 1\nself.at(" + call + ")", TIMING)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(fragment, errors[0])
                self.assertIn("line 2", errors[0])
        self.assertEqual(scenes.check_helpers("self.at(S(1))\nself.at(W(1, 'cell'))", TIMING), ([], 2))

    def test_starting_page(self) -> None:
        """manim_scene.render_starting_page fills assets/manim_scene.py with the beats quoted as Python, the
        background colour, a ValueTracker-driven movement and finish(), and the page compiles and passes the
        helper check. Guards the starting scene.py."""
        scene = {"id": "plot", "engine": "manim", "brief": "b", "beats": ['label "cell"', "it's it"]}
        page = manim_scene.render_starting_page(scene)
        self.assertNotIn("__", page.replace("__file__", ""))
        self.assertIn("class Main(TimedScene):", page)
        self.assertIn("""BEATS = ['label "cell"', "it's it"]""", page)
        self.assertIn("BACKGROUND_COLOR = '#0b1320'", page)
        self.assertIn("self.finish()", page)
        self.assertIn("ValueTracker(0)", page)
        compile(page, "scene.py", "exec")
        self.assertEqual(manim_scene.check_scene_py(page, TIMING)[0], [])

    def test_scene_class_and_colour(self) -> None:
        """manim_scene.render_starting_page and manim_command use `manim.scene_class` and `background_color`
        from settings, quoting the colour, and refuse a class name that is not a Python identifier. Guards
        settings values inserted into Python source and the command line."""
        scene = {"id": "plot", "engine": "manim", "brief": "b", "beats": ["x"]}
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            try:
                (project / "settings.yaml").write_text('manim: {background_color: \'say "hi"\', scene_class: Plot}\n')
                settings.use_project(project)
                page = manim_scene.render_starting_page(scene)
                self.assertIn("class Plot(TimedScene):", page)
                self.assertIn("""BACKGROUND_COLOR = 'say "hi"'""", page)
                compile(page, "scene.py", "exec")
                self.assertIn("`render` renders class `Plot`", manim_scene.manim_brief(scene, TIMING, "v1"))
                for bad in ("my scene", "1st", "class", 3):
                    with self.subTest(bad=bad):
                        (project / "settings.yaml").write_text(f"manim: {{scene_class: {json.dumps(bad)}}}\n")
                        settings.use_project(project)
                        with self.assertRaisesRegex(scenes.SceneError, "must be a Python class name"):
                            manim_scene.render_starting_page(scene)
                        with self.assertRaisesRegex(scenes.SceneError, "must be a Python class name"):
                            manim_scene.manim_command(project)
            finally:
                settings.use_project(None)

    def test_length_ok(self) -> None:
        """manim_scene.length_ok accepts a video within manim.length_tolerance_frames of the narration and
        refuses one more. Guards render's length check."""
        self.assertTrue(manim_scene.length_ok(137 / 30, 4.5667))
        self.assertTrue(manim_scene.length_ok(138 / 30, 4.5667))
        self.assertFalse(manim_scene.length_ok(139 / 30, 4.5667))

    def test_command_and_env(self) -> None:
        """manim_scene.manim_command runs `uv run --project scripts/manim` at the video size on scene.py, and
        manim_env_vars drops VIRTUAL_ENV, sets UV_PROJECT_ENVIRONMENT next to PLUGIN_ENV_DIR and refuses without
        it. Guards the Manim environment staying outside the plugin directory."""
        cmd = manim_scene.manim_command(Path("/p/scenes/x/v1"))
        self.assertEqual(cmd[1:4], ["run", "--project", str(config.MANIM_PROJECT)])
        self.assertIn("1920,1080", cmd)
        self.assertEqual(cmd[-2:], ["/p/scenes/x/v1/scene.py", "Main"])
        imports = "from short_video_tool import manim_scene"
        env = py_value(imports, "manim_scene.manim_env_vars({'VIRTUAL_ENV': '/v', 'PATH': '/bin'})",
                       child_env({"HOME": "/nonexistent", "PLUGIN_ENV_DIR": "/d/env/123/short-video"}))
        self.assertEqual(env, {"PATH": "/bin", "UV_PROJECT_ENVIRONMENT": "/d/env/123/short-video-scripts-manim/.venv"})
        done = run_python(f"{imports}\nmanim_scene.manim_env_vars()", child_env({"HOME": "/nonexistent"}))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("PLUGIN_ENV_DIR", done.stderr)


class TestScaffold(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name)
        (p / "images").mkdir()
        (p / "images" / "a.png").write_bytes(b"png")
        vdir = versions.next_version(state.voice_root(p, "plot"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        state.write_meta(vdir, {"duration": TIMING["duration"]})
        self.scene = storyboard.parse_markdown(MD)["scenes"][0]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scaffold_files(self) -> None:
        """manim_scene.scaffold writes brief.md, scene.py, sv_timing.py, timing.json and voice_version into
        scenes/<id>/v1, the brief noting no image and the Manim reference. Guards the manim scene version
        layout."""
        out = manim_scene.scaffold(self.project, self.scene)
        self.assertEqual(out, self.project / "scenes" / "plot" / "v1")
        self.assertEqual(sorted(f.name for f in out.iterdir()),
                         ["brief.md", "scene.py", "sv_timing.py", "timing.json", "voice_version"])
        self.assertEqual((out / "voice_version").read_text(), "v1\n")
        self.assertEqual(json.loads((out / "timing.json").read_text()), TIMING)
        brief = (out / "brief.md").read_text()
        self.assertIn("- Image: none", brief)
        self.assertIn("Draw the curve.", brief)
        self.assertIn("## Manim", brief)
        self.assertIn("references/manim.md", brief)
        self.assertIn('BEATS = [\'curve drawn on "rises"\']', (out / "scene.py").read_text())

    def test_rescaffold_keeps_scene_py_and_copies_image(self) -> None:
        """manim_scene.scaffold copies the edited scene.py from the latest version and copies the scene image as
        background. Guards a re-scaffold losing the agent's edits."""
        first = manim_scene.scaffold(self.project, self.scene)
        (first / "scene.py").write_text("# edited\n")
        scene = dict(self.scene, image="a.png")
        second = manim_scene.scaffold(self.project, scene)
        self.assertEqual(second.name, "v2")
        self.assertEqual((second / "scene.py").read_text(), "# edited\n")
        self.assertEqual((second / scenes.BACKGROUND).read_bytes(), b"png")

    def test_refusals(self) -> None:
        """manim_scene.scaffold refuses a non-manim scene, a scene without voice and a missing image, and
        manim_scene.render refuses a scene never scaffolded. Guards the order scaffold, then render."""
        with self.assertRaisesRegex(scenes.SceneError, "not a manim scene"):
            manim_scene.scaffold(self.project, {"id": "plot", "image": "a.png"})
        with self.assertRaisesRegex(scenes.SceneError, "no voice yet"):
            manim_scene.scaffold(self.project, dict(self.scene, id="other"))
        with self.assertRaisesRegex(scenes.SceneError, "nothing.png not found"):
            manim_scene.scaffold(self.project, dict(self.scene, image="nothing.png"))
        with self.assertRaisesRegex(scenes.SceneError, "run `scaffold` first"):
            manim_scene.render(self.project, self.scene)


class TestRenderSwitchedToHtml(unittest.TestCase):
    """A scene switched from manim to html, rendered before `scaffold`."""

    def test_render_asks_for_scaffold(self) -> None:
        """cli render of a scene switched from manim to html, whose latest version has no index.html, stops and
        asks for scaffold. Guards rendering a manim version as HTML."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "images").mkdir()
            (p / "images" / "a.png").write_bytes(b"png")
            (p / "settings.yaml").write_text("author: [Jane Doe]\n")
            (p / "storyboard.md").write_text(MD)
            vdir = versions.next_version(state.voice_root(p, "plot"))
            (vdir / "timing.json").write_text(json.dumps(TIMING))
            state.write_meta(vdir, {"duration": TIMING["duration"]})
            settings.use_project(p)
            try:
                manim_scene.scaffold(p, storyboard.parse_markdown(MD)["scenes"][0])
                (p / "storyboard.md").write_text(MD.replace("Engine: manim\nBrief: Draw", "Engine: html\n"
                                                            "Image: a.png\nBrief: Draw", 1))
                args = argparse.Namespace(project=str(p), scene="plot")
                err = io.StringIO()
                with redirect_stderr(err), self.assertRaises(SystemExit):
                    cli._cmd_render(args)
            finally:
                settings.use_project(None)
            self.assertIn("scene plot: latest version v1 has no index.html; run `scaffold` first", err.getvalue())


if __name__ == "__main__":
    unittest.main()
