"""short_video_tool.scenes: the static check of timing-helper calls, filled
starting pages, card.js, scene length, contact sheet and background videos."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import scenes


def _sentence(i: int, text: str, start: float) -> dict:
    words = [{"text": w, "start": start + k * 0.3, "end": start + k * 0.3 + 0.25} for k, w in enumerate(text.split())]
    return {"index": i, "text": text, "start": start, "end": words[-1]["end"], "words": words}


TIMING = {"duration": 6.2, "sentences": [
    _sentence(1, "A virus enters the cell.", 0.25),
    _sentence(2, "The cell copies the virus, virus after Virus.", 2.45),
]}


class TestCheckHelpers(unittest.TestCase):

    def test_calls(self) -> None:
        """scenes.check_helpers accepts literal S/SE/W/WE calls that match timing.json, ignores non-literal and
        other-name calls, and reports an unknown word, a missing occurrence, a missing sentence and a wrong
        argument count with the line. Guards render's static helper check against the voiced timing."""
        ok = 'S(1); SE(2); W(1, "virus"); WE(2, \'virus\', 3); W( 1 , "CELL" ); S(i); W(1, label); CSS(9); obj.S(9)'
        self.assertEqual(scenes.check_helpers(ok, TIMING), ([], 5))
        for call, fragment in [('W(1, "bacteria")', "not found"), ('W(2, "virus", 4)', "3 occurrence"),
                               ("S(3)", "no sentence"), ('W(5, "virus")', "no sentence"), ("S(1, 2)", "takes one")]:
            with self.subTest(call=call):
                errors, _ = scenes.check_helpers("\n" + call, TIMING)
                self.assertEqual(len(errors), 1)
                self.assertIn(fragment, errors[0])
                self.assertIn("line 2", errors[0])


class TestPages(unittest.TestCase):

    def test_filled_pages(self) -> None:
        """scenes.render_template fills every starting page (scene, title, summary, end) with no placeholder
        left, registers the timeline under the scene id and passes check_helpers. Guards the asset pages
        rendering as given."""
        for kind in ("scene", "title", "summary", "end"):
            with self.subTest(kind=kind):
                html = scenes.render_template(kind, 5.0, kind)
                self.assertNotIn("__", html.replace("window.__timelines", ""))
                self.assertIn(f'window.__timelines["{kind}"] = tl', html)
                self.assertIn('data-composition-id="' + kind + '"', html)
                self.assertEqual(scenes.check_helpers(html, TIMING)[0], [])

    def test_set_full_length_rewrites_only_marked_tags(self) -> None:
        """scenes.set_full_length rewrites data-duration only on tags marked data-full-length. Guards overlays
        keeping their own durations when the scene length changes."""
        html = scenes.render_template("intro", 6.2).replace(
            "<!-- overlays here -->", '<div id="lbl" data-start="1" data-duration="6.2"></div>')
        out = scenes.set_full_length(html, 9.75)
        self.assertEqual(out.count('data-duration="9.75"'), html.count('data-duration="6.2"') - 1)
        self.assertIn('id="lbl" data-start="1" data-duration="6.2"', out)

    def test_card_js(self) -> None:
        """scenes.card_js writes the card rows, author, byline and credit as JSON with `</script>` escaped.
        Guards card text that would close the script tag."""
        js = scenes.card_js({"template": "end", "author": "Jane O'Doe", "beats": ["A </script> & more"]})
        self.assertNotIn("</script>", js)
        card = json.loads(re.search(r"\{.*\}", js, re.S).group(0).replace("<\\/", "</"))
        self.assertEqual(card, {"rows": ["A </script> & more"], "author": "Jane O'Doe", "image": False,
                                "byline": "by Jane O'Doe", "credit": "Created by Jane O'Doe"})

    def test_lengths(self) -> None:
        """scenes.scene_duration adds a template's hold_seconds to the narration and scenes.contact_sheet_filter
        picks the tile grid for a 12.3 s scene. Guards template scenes lasting past their narration."""
        self.assertEqual(scenes.scene_duration({"template": "end"}, 5.0), 9.0)
        self.assertEqual(scenes.scene_duration({"image": "a.png"}, 5.0), 5.0)
        self.assertEqual(scenes.contact_sheet_filter(12.3), "fps=1,scale=384:-2,tile=5x3")

    def test_doctor_judges_required_checks_only(self) -> None:
        """scenes.doctor_failures reports failed required HyperFrames doctor checks only, with their detail.
        Guards setup failing on an optional check such as Docker."""
        report = {"checks": [{"name": n, "ok": True} for n in ("Node.js", "FFmpeg", "FFprobe")]
                  + [{"name": "Chrome", "ok": False, "detail": "missing"}, {"name": "Docker", "ok": False}]}
        self.assertEqual(scenes.doctor_failures(report), ["Chrome: missing"])


class TestBackgroundVideo(unittest.TestCase):

    PAGE = ('<video id="bg-video" class="clip bg" src="background.mp4" muted playsinline\n'
            '       data-start="0" data-duration="6.2" data-full-length></video><img src="background.png">')

    def test_sources(self) -> None:
        """scenes.video_sources lists <video> sources and ignores images. Guards which files check_videos
        checks."""
        self.assertEqual(scenes.video_sources(self.PAGE), ["background.mp4"])
        self.assertEqual(scenes.video_sources("<img src='a.png'>"), [])

    def test_missing_and_short_files(self) -> None:
        """scenes.check_videos reports a missing background video and one shorter than the scene by more than a
        frame, suggesting tpad, and accepts one within a frame or longer. Guards render failing on a background
        video that ends early."""
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp)
            self.assertIn("not found", scenes.check_videos(sdir, self.PAGE, 6.2, 30)[0])
            for length, n_errors in ((6.2, 0), (10.0, 0), (4.0, 1)):
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                                f"color=c=black:s=16x16:r=30:d={length}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                str(sdir / "background.mp4")], check=True)
                with self.subTest(length=length):
                    errors = scenes.check_videos(sdir, self.PAGE, 6.2, 30)
                    self.assertEqual(len(errors), n_errors)
            self.assertIn("tpad", errors[0])

    def test_scaffold_carries_the_video_forward(self) -> None:
        """scenes.scaffold copies the previous version's background video, and every file and subdirectory the
        author added (fonts/), into the next version, and leaves generated ones (stills/) behind
        (references/scenes.md, "Procedure"). Guards a re-scaffold losing the scene's background video or fonts."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir = Path(tmp, "p"), Path(tmp, "node")
            voice = project / "voice" / "s" / "v1"
            voice.mkdir(parents=True)
            (voice / "timing.json").write_text(json.dumps(TIMING), encoding="utf-8")
            (voice / "meta.json").write_text("{}", encoding="utf-8")
            (node_dir / scenes.GSAP_REL).parent.mkdir(parents=True)
            (node_dir / scenes.GSAP_REL).write_text("x", encoding="utf-8")
            scene = {"id": "s", "brief": "b", "beats": []}
            first = scenes.scaffold(project, scene, node_dir)
            self.assertFalse((first / scenes.BACKGROUND_VIDEO).exists())
            (first / scenes.BACKGROUND_VIDEO).write_bytes(b"clip")
            (first / "fonts").mkdir()
            (first / "fonts" / "Barlow.ttf").write_bytes(b"font")
            (first / "stills").mkdir()
            (first / "stills" / "at_000.000.png").write_bytes(b"png")
            second = scenes.scaffold(project, scene, node_dir)
            self.assertEqual((second / scenes.BACKGROUND_VIDEO).read_bytes(), b"clip")
            self.assertEqual((second / "fonts" / "Barlow.ttf").read_bytes(), b"font")
            self.assertFalse((second / "stills").exists())


def _project(tmp: str) -> tuple[Path, Path]:
    """A project with one voice version of scene `s` and a GSAP stub; returns (project, node_dir)."""
    project, node_dir = Path(tmp, "p"), Path(tmp, "node")
    voice = project / "voice" / "s" / "v1"
    voice.mkdir(parents=True)
    (voice / "timing.json").write_text(json.dumps(TIMING), encoding="utf-8")
    (voice / "meta.json").write_text("{}", encoding="utf-8")
    (node_dir / scenes.GSAP_REL).parent.mkdir(parents=True)
    (node_dir / scenes.GSAP_REL).write_text("x", encoding="utf-8")
    return project, node_dir


class TestWithoutImage(unittest.TestCase):

    def test_scaffold_without_image(self) -> None:
        """scenes.scaffold of an HTML scene without an image starts from assets/scene-drawn.html: a page with
        #bg-fill and #anchored, no #bg-image and no background.png, and brief.md says Image: none; with an
        image it starts from scene.html. Guards scenes drawn in the page with no picture."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir = _project(tmp)
            out = scenes.scaffold(project, {"id": "s", "brief": "A bar chart grows.", "beats": ["bar"]}, node_dir)
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="bg-fill"', html)
            self.assertIn('id="anchored"', html)
            self.assertNotIn("bg-image", html)
            self.assertNotIn(scenes.BACKGROUND, html)
            self.assertFalse((out / scenes.BACKGROUND).exists())
            self.assertIn("- Image: none", (out / "brief.md").read_text(encoding="utf-8"))
            self.assertEqual(scenes.check_background(out, html, {"id": "s"}), [])
            self.assertEqual(scenes.page_kind({"id": "s", "image": "a.png"}), "scene")
            self.assertEqual(scenes.page_kind({"id": "s", "template": "end"}), "end")

    def test_page_using_a_missing_background(self) -> None:
        """scenes.check_background reports a scene page that uses background.png when the version has none (an
        image removed from the storyboard), and accepts it with the file or on a template page. Guards render
        showing a broken picture."""
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp)
            page = scenes.render_template("s", 6.2, "scene")
            self.assertIn("no image", scenes.check_background(sdir, page, {"id": "s"})[0])
            self.assertEqual(scenes.check_background(sdir, page, {"id": "t", "template": "title"}), [])
            (sdir / scenes.BACKGROUND).write_bytes(b"png")
            self.assertEqual(scenes.check_background(sdir, page, {"id": "s"}), [])


class TestNodeReady(unittest.TestCase):

    def _install(self, node_dir: Path) -> None:
        for rel in (scenes.HYPERFRAMES_REL, scenes.GSAP_REL):
            (node_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (node_dir / rel).write_text("x", encoding="utf-8")

    def test_package_files_must_match_source(self) -> None:
        """scenes.node_ready is false until the installed package.json and package-lock.json equal scripts/node/
        and false again after the lock changes. Guards render rerunning npm ci when the pinned versions change."""
        with tempfile.TemporaryDirectory() as tmp:
            src, node_dir = Path(tmp, "src"), Path(tmp, "env", "node")
            src.mkdir()
            for f in scenes.NODE_FILES:
                (src / f).write_text("{}", encoding="utf-8")
            self._install(node_dir)
            self.assertFalse(scenes.node_ready(node_dir, src))
            for f in scenes.NODE_FILES:
                shutil.copyfile(src / f, node_dir / f)
            self.assertTrue(scenes.node_ready(node_dir, src))
            (src / "package-lock.json").write_text('{"v": 2}', encoding="utf-8")
            self.assertFalse(scenes.node_ready(node_dir, src))

    def test_in_place_install_needs_no_source(self) -> None:
        """scenes.node_ready without a source directory checks only that HyperFrames and GSAP are installed.
        Guards the in-place install next to the package files."""
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp)
            self.assertFalse(scenes.node_ready(node_dir))
            self._install(node_dir)
            self.assertTrue(scenes.node_ready(node_dir))


if __name__ == "__main__":
    unittest.main()


class TestEstimate(unittest.TestCase):

    SCENE = {"id": "s", "brief": "A bar chart grows.", "narration": ["Sales grew fast.", "Then they fell back."],
             "beats": ["bar", "fall"]}

    def test_scaffold_from_the_words(self) -> None:
        """scenes.scaffold with estimate times a narrated scene from its words at length.words_per_second (2.5)
        without a voice version: timing.json holds `estimated`, the words follow one another, brief.md says the
        narration is not recorded, the version has no voice_version, render refuses it and status gives a render
        reason; a silent scene is refused. A plain scaffold after the voice is timed from the recording. Guards a
        drawn scene's first page built before the storyboard is voiced."""
        from short_video_tool import status
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir = _project(tmp)
            shutil.rmtree(project / "voice")
            out = scenes.scaffold(project, self.SCENE, node_dir, estimate=True)
            timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
            self.assertEqual(timing["estimated"], 2.5)
            self.assertEqual(timing["duration"], 2.8)
            self.assertEqual([s["start"] for s in timing["sentences"]], [0.0, 1.2])
            self.assertEqual(timing["sentences"][1]["words"][0], {"text": "Then", "start": 1.2, "end": 1.6})
            self.assertIn("2.5 words per second", (out / "timing.js").read_text(encoding="utf-8"))
            self.assertIn("not recorded", (out / "brief.md").read_text(encoding="utf-8"))
            self.assertFalse((out / "voice_version").exists())
            with self.assertRaisesRegex(scenes.SceneError, "estimate"):
                scenes.render(project, self.SCENE, node_dir)
            self.assertTrue(any("estimate" in r for r in status.render_reasons(project, self.SCENE)))
            with self.assertRaisesRegex(scenes.SceneError, "narrated"):
                scenes.scaffold(project, {"id": "s", "brief": "b", "length": 3}, node_dir, estimate=True)
            voice = project / "voice" / "s" / "v1"
            voice.mkdir(parents=True)
            (voice / "timing.json").write_text(json.dumps(TIMING), encoding="utf-8")
            (voice / "meta.json").write_text("{}", encoding="utf-8")
            second = scenes.scaffold(project, self.SCENE, node_dir)
            self.assertNotIn("estimated", json.loads((second / "timing.json").read_text(encoding="utf-8")))
            self.assertEqual((second / "voice_version").read_text().strip(), "v1")
            self.assertFalse(any("estimate" in r for r in status.render_reasons(project, self.SCENE)))
