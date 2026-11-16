"""short_video_tool: silent HTML scenes (`Length:`) and shared worlds (`World:`): storyboard keys and checks,
frame-aligned world times, the world timing check, scaffold and status."""
import json
import tempfile
import unittest
from pathlib import Path

from short_video_tool import scenes, settings, state, status, storyboard, versions, world

HEAD = "# W\n\nTopic: t.\n\n"
TABLE = "| Narration | On screen |\n|---|---|\n| {text} | {beat} |\n"


def _md(*sections: str) -> str:
    return HEAD + "\n".join(sections)


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


def _sentence(i: int, text: str, start: float) -> dict:
    words = [{"text": w, "start": start + k * 0.3, "end": start + k * 0.3 + 0.25} for k, w in enumerate(text.split())]
    return {"index": i, "text": text, "start": start, "end": words[-1]["end"], "words": words}


class TestStoryboardKeys(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_parse_length_and_world(self) -> None:
        """storyboard.parse_markdown reads `Length:` as a number of seconds (with or without `s`) on a scene without
        a table, and `World:` as the scene's world. Guards the silent HTML scene and the shared world keys."""
        data = storyboard.parse_markdown(_md("## a\nBrief: Fly in.\nLength: 4.5\nWorld: city\n",
                                             "## b\nBrief: Fly on.\nWorld: city\n\n" + TABLE.format(text="Hi.", beat="on")))
        self.assertEqual(data["scenes"][0], {"id": "a", "brief": "Fly in.", "length": 4.5, "world": "city",
                                             "narration": [], "beats": []})
        self.assertEqual(data["scenes"][1]["world"], "city")
        self.assertEqual(storyboard.parse_markdown(_md("## a\nBrief: x.\nLength: 3s\n"))["scenes"][0]["length"], 3.0)
        self.assertFalse(storyboard.narrated(data["scenes"][0]))
        self.assertEqual(storyboard.length_seconds(data["scenes"][0]), 4.5)
        self.assertEqual([s["id"] for s in storyboard.world_of(data, data["scenes"][1])], ["a", "b"])
        self.assertIsNone(storyboard.world_of(data, {"id": "c"}))

    def test_length_errors(self) -> None:
        """storyboard.parse_markdown refuses a Length that is not a positive number, a Length with a table, on a
        template or manim scene, and an HTML scene with neither table nor Length. Guards silent scenes being only
        HTML scenes without narration."""
        cases = [
            ("## a\nBrief: x.\nLength: soon\n", "number of seconds"),
            ("## a\nBrief: x.\nLength: 0\n", "number of seconds"),
            ("## a\nBrief: x.\nLength: 2\n\n" + TABLE.format(text="Hi.", beat="on"), "is silent and has no narration"),
            ("## a\nTemplate: title\nLength: 2\n\n" + TABLE.format(text="Hi.", beat="T"), "only an HTML scene"),
            ("## a\nEngine: manim\nBrief: x.\nLength: 2\n", "only an HTML scene"),
            ("## a\nBrief: x.\n", "scene with `Length:` may have none"),
        ]
        for text, fragment in cases:
            with self.subTest(text=text):
                self.assertIn(fragment, _error(_md(text)))

    def test_world_errors(self) -> None:
        """storyboard.check refuses a world whose scenes are not consecutive, an invalid world name, and a world
        scene with an image, a template or another engine. Guards the cut of one page into consecutive scenes."""
        def scene(sid: str, **kw) -> dict:
            return {"id": sid, "brief": "b", "length": 2, "narration": [], "beats": [], **kw}

        def problems(*sc: dict) -> str:
            return " ".join(m for _, m in storyboard.check({"title": "T", "topic": "t", "scenes": list(sc)}))

        self.assertEqual(problems(scene("a", world="w"), scene("b", world="w"), scene("c")), "")
        self.assertIn("must be consecutive", problems(scene("a", world="w"), scene("b"), scene("c", world="w")))
        self.assertIn("invalid `world`", problems(scene("a", world="City")))
        self.assertIn("world scene is an HTML scene", problems(scene("a", world="w", image="a.png")))
        self.assertIn("world scene is an HTML scene",
                      problems({"id": "a", "brief": "b", "engine": "manim", "world": "w", "narration": ["X."],
                                "beats": ["x"]}))

    def test_world_of_one_scene_warns(self) -> None:
        """storyboard.validate warns about a world of one scene and estimates a silent scene at its Length.
        Guards a World key that joins nothing, and the length estimate of silent scenes."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / storyboard.MD_FILE).write_text(_md("## a\nBrief: x.\nLength: 7\nWorld: w\n"), encoding="utf-8")
            data = storyboard.load(project)
            v = storyboard.validate(data, project)
            self.assertTrue(v.ok, v.errors)
            self.assertTrue(any("world 'w' has one scene" in w for w in v.warnings), v.warnings)
            self.assertEqual(v.estimated_seconds, 7.0)


class TestWorldTiming(unittest.TestCase):

    def test_frame_starts(self) -> None:
        """world.frame_starts rounds each cumulative end to a whole frame. Guards scene starts landing on frames,
        so the cuts join frame to frame."""
        self.assertEqual(world.frame_starts([1.0, 1.01, 0.5], 30), [0, 30, 60, 75])
        self.assertEqual(world.frame_starts([0.333, 0.333, 0.334], 30), [0, 10, 20, 30])

    def test_seconds_attr_renders_exact_frames(self) -> None:
        """world.seconds_attr writes a length that HyperFrames' frame count (round within 0.001 frame, else
        ceil) turns into exactly that many frames. Guards a world render one frame too long."""
        for frames in range(1, 400):
            raw = float(world.seconds_attr(frames, 30)) * 30
            count = round(raw) if abs(raw - round(raw)) <= 1e-3 else -(-raw // 1)
            self.assertEqual(count, frames)

    def test_check_helpers_world(self) -> None:
        """scenes.check_helpers on a world timing accepts calls naming a scene of the world, and reports an
        unqualified call, an unknown scene, a sentence the scene lacks and a word not in it; on a scene page it
        reports ST. Guards render's static check of a world page."""
        timing = {"duration": 6.0, "scenes": [
            {"id": "a", "start": 0, "end": 3, "sentences": [_sentence(1, "A virus enters.", 0.2)]},
            {"id": "b", "start": 3, "end": 6, "sentences": []}]}
        ok = 'ST("a"); STE("b"); S("a", 1); SE(\'a\', 1); W("a", 1, "virus"); WE("a", 1, "enters", 1); S(id, 1)'
        self.assertEqual(scenes.check_helpers(ok, timing), ([], 6))
        for call, fragment in [("S(1)", "names the scene first"), ('ST("c")', "no scene 'c'"),
                               ('S("b", 1)', "no sentence 1 of scene 'b'"), ('W("a", 1, "cell")', "not found"),
                               ('ST("a", 1)', "takes one scene id")]:
            with self.subTest(call=call):
                errors, _ = scenes.check_helpers(call, timing)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(fragment, errors[0])
        self.assertIn("only in a world page", scenes.check_helpers('ST("a")', {"duration": 1, "sentences": []})[0][0])

    def test_world_page_passes_its_check(self) -> None:
        """The starting page assets/world.html, filled, has no placeholder left, registers the timeline under the
        world name and passes check_helpers with a world timing. Guards the world starting page rendering as
        given."""
        html = scenes.render_template("city", "6.033333", world.PAGE)
        self.assertNotIn("__", html.replace("window.__timelines", ""))
        self.assertIn('window.__timelines["city"] = tl', html)
        self.assertIn('data-duration="6.033333"', html)
        self.assertEqual(scenes.check_helpers(html, {"duration": 1, "scenes": [{"id": "a", "sentences": []}]}),
                         ([], 0))


def _project(tmp: str, md: str) -> tuple[Path, Path, dict]:
    project, node_dir = Path(tmp, "p"), Path(tmp, "node")
    project.mkdir()
    (project / storyboard.MD_FILE).write_text(md, encoding="utf-8")
    (node_dir / scenes.GSAP_REL).parent.mkdir(parents=True)
    (node_dir / scenes.GSAP_REL).write_text("x", encoding="utf-8")
    return project, node_dir, storyboard.load(project)


class TestScaffold(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_silent_scene_scaffold(self) -> None:
        """scenes.scaffold of a silent HTML scene needs no voice: timing.json has its Length and no sentences,
        there is no voice_version file, and brief.md says it is silent. Guards `Length:` scenes rendering without
        narration."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp, _md("## a\nBrief: A title fades in.\nLength: 2.5\n"))
            out = scenes.scaffold(project, data["scenes"][0], node_dir)
            self.assertEqual(json.loads((out / "timing.json").read_text()), {"duration": 2.5, "sentences": []})
            self.assertFalse((out / "voice_version").exists())
            self.assertIn('data-duration="2.5"', (out / "index.html").read_text())
            self.assertIn("none (silent), Length 2.50 s", (out / "brief.md").read_text())

    def test_world_scaffold_carries_files_and_refresh(self) -> None:
        """world.scaffold carries a subdirectory the author added (fonts/) into the next world version;
        `refresh` rewrites brief.md of the latest version in place after a Brief edit, keeping the page and
        refusing a rendered version (references/scenes.md, "Worlds"). Guards fonts lost across world versions and
        a new version forced by a Brief edit before the page is written."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp, _md("## a\nBrief: Wide.\nLength: 2\nWorld: city\n"))
            first = world.scaffold(project, data, "city", node_dir)
            (first / "fonts").mkdir()
            (first / "fonts" / "Barlow.ttf").write_bytes(b"font")
            second = world.scaffold(project, data, "city", node_dir)
            self.assertEqual(second.name, "v2")
            self.assertEqual((second / "fonts" / "Barlow.ttf").read_bytes(), b"font")
            (second / "index.html").write_text((second / "index.html").read_text() + "<!-- page -->")
            (project / storyboard.MD_FILE).write_text(_md("## a\nBrief: Close.\nLength: 2\nWorld: city\n"))
            edited = storyboard.load(project)
            same = world.scaffold(project, edited, "city", node_dir, refresh=True)
            self.assertEqual(same, second)
            self.assertIn("Close.", (same / "brief.md").read_text())
            self.assertIn("<!-- page -->", (same / "index.html").read_text())
            (same / "silent.mp4").write_bytes(b"")
            with self.assertRaisesRegex(scenes.SceneError, "is rendered"):
                world.scaffold(project, edited, "city", node_dir, refresh=True)

    def test_world_scaffold_and_status(self) -> None:
        """world.scaffold lays the world's scenes out frame-aligned (a narrated scene at its voice length, a silent
        one at its Length), writes world.json, a world timing.js with absolute sentence times and brief.md; status
        reports the scaffolded world current with no render, and a new voice version makes the rendered world stale.
        Guards the shared world layout and its staleness."""
        md = _md("## a\nBrief: Wide.\nLength: 1.01\nWorld: city\n",
                 "## b\nBrief: Push in.\nWorld: city\n\n" + TABLE.format(text="A virus enters.", beat='on "virus"'))
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir, data = _project(tmp, md)
            vdir = versions.next_version(state.voice_root(project, "b"))
            (vdir / "timing.json").write_text(json.dumps({"duration": 2.0, "sentences": [
                _sentence(1, "A virus enters.", 0.2)]}))
            state.write_meta(vdir, {})
            wdir = world.scaffold(project, data, "city", node_dir)
            self.assertEqual(wdir, project / "worlds" / "city" / "v1")
            plan = json.loads((wdir / world.WORLD_JSON).read_text())
            fps = settings.get()["video"]["fps"]
            f1 = round(1.01 * fps)
            self.assertEqual([s["frames"] for s in plan["scenes"]], [[0, f1], [f1, round(3.01 * fps)]])
            self.assertEqual([s["voice_version"] for s in plan["scenes"]], [None, "v1"])
            timing = json.loads((wdir / "timing.json").read_text())
            self.assertAlmostEqual(timing["scenes"][1]["sentences"][0]["start"], f1 / fps + 0.2, places=5)
            self.assertIn("window.TIMING", (wdir / "timing.js").read_text())
            self.assertIn('S("b", 1)=', (wdir / "brief.md").read_text())
            html = (wdir / "index.html").read_text()
            self.assertIn('data-composition-id="city"', html)
            self.assertIn(f'data-duration="{world.seconds_attr(round(3.01 * fps), fps)}"', html)

            # The scaffolded world plays in the HTML film: nothing to redo, and no render.
            report = status.report(project, data)["scenes"]
            self.assertEqual([(s["render_reasons"], s["rendered"]) for s in report], [([], False)] * 2)

            # A rendered world as world.render leaves it, then a new voice version of b.
            state.write_meta(wdir, {"world": "city"})
            for span in plan["scenes"]:
                sdir = versions.next_version(state.scene_root(project, span["id"]))
                state.write_meta(sdir, {"scene": span["id"], "world": "city", "world_version": "v1"})
            self.assertEqual([(s["render_reasons"], s["rendered"]) for s in status.report(project, data)["scenes"]],
                             [([], True)] * 2)
            v2 = versions.next_version(state.voice_root(project, "b"))
            (v2 / "timing.json").write_text(json.dumps({"duration": 2.5, "sentences": [
                _sentence(1, "A virus enters.", 0.2)]}))
            state.write_meta(v2, {})
            for s in status.report(project, data)["scenes"]:
                self.assertTrue(s["needs_render"], s)
                self.assertIn("voice versions or lengths changed", s["render_reasons"][0])


if __name__ == "__main__":
    unittest.main()
