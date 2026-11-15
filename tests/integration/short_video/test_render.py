"""Integration test for scaffold + render with the real HyperFrames renderer.

A 2-second scene is scaffolded from a hand-made voice version (a tone WAV and
its timing.json; the voiceover skill is not used), given one label animated
with the W()/S() helpers, and rendered.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, media, scenes, settings, state, status, storyboard, versions
from tests.prereq import requires
from tests.integration.short_video.wrapper_env import NODE_DIR

DURATION = 2.0
TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": DURATION,
    "model": "kokoro:kokoro-v1.0", "voice": "af_heart", "speed": 1.0,
    "sentences": [{
        "index": 1, "text": "Hello world.", "start": 0.25, "end": 1.4, "aligned": True,
        "words": [{"text": "Hello", "start": 0.25, "end": 0.7}, {"text": "world.", "start": 0.75, "end": 1.4}],
    }],
}
LABEL = """<div id="label" style="position:absolute;left:120px;top:120px;padding:24px 40px;
  background:#fff;color:#000;font-size:72px;opacity:0">world</div>
  <!-- overlays here -->"""
ANIMATION = """const tl = gsap.timeline({ paused: true });
  tl.to("#label", { opacity: 1, duration: 0.2 }, W(1, "world"));
  tl.to("#label", { x: 200, duration: 0.3 }, SE(1));"""


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "render_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1200x900", "-frames:v", "1", str(p / "images" / "cell.png"))
        cls.scene = {"id": "intro", "image": "cell.png", "brief": "Label the word.",
                     "narration": ["Hello world."], "beats": ["label appears on 'world'"]}
        (p / "storyboard.md").write_text(
            "# Render test\n\nTopic: Rendering.\n\n## intro\n\nImage: cell.png\nBrief: Label the word.\n\n"
            "| Narration | On screen |\n|---|---|\n| Hello world. | label appears on 'world' |\n",
            encoding="utf-8",
        )
        data = storyboard.load(p)
        assert data["scenes"] == [cls.scene]

        vdir = versions.next_version(state.voice_root(p, "intro"))
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={DURATION}",
                str(vdir / "narration.wav"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        state.write_meta(vdir, {"duration": DURATION})

        cls.sdir = scenes.scaffold(p, cls.scene, NODE_DIR)
        html = (cls.sdir / "index.html").read_text()
        html = html.replace("<!-- overlays here -->", LABEL)
        html = html.replace("const tl = gsap.timeline({ paused: true });", ANIMATION)
        (cls.sdir / "index.html").write_text(html)
        cls.scene_mp4 = scenes.render(p, cls.scene, NODE_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_scaffold_layout(self) -> None:
        """scenes.scaffold writes index.html, timing.js, gsap.min.js, background.png and brief.md into
        scenes/<id>/v1, the brief holding the narration. Guards the HyperFrames project layout render needs."""
        self.assertEqual(self.sdir, self.project / "scenes" / "intro" / "v1")
        for name in ("index.html", "timing.js", "gsap.min.js", "background.png", "brief.md"):
            self.assertTrue((self.sdir / name).is_file(), name)
        self.assertIn("world.", (self.sdir / "brief.md").read_text())

    def test_sixty_frames_at_1080p(self) -> None:
        """scenes.render of a 2 s scene gives 60 frames at 1920x1080 with the real HyperFrames. Guards the scene
        length rewritten into data-duration and the `video:` size."""
        video = next(s for s in media.probe(self.scene_mp4)["streams"] if s["codec_type"] == "video")
        self.assertEqual(int(video["nb_frames"]), 60)
        self.assertEqual((video["width"], video["height"]), (1920, 1080))

    def test_narration_muxed(self) -> None:
        """scenes.render muxes the narration into scene.mp4 at the scene length. Guards the apad,atrim mux,
        since -shortest never ends with stream copy."""
        streams = media.probe(self.scene_mp4)["streams"]
        self.assertEqual(sorted(s["codec_type"] for s in streams), ["audio", "video"])
        self.assertAlmostEqual(media.duration(self.scene_mp4), DURATION, delta=0.05)

    def test_contact_sheet(self) -> None:
        """scenes.render writes contact.png five 384 px tiles wide. Guards the contact sheet the scene critic
        reads."""
        contact = self.sdir / "contact.png"
        self.assertTrue(contact.is_file())
        img = media.probe(contact)["streams"][0]
        self.assertEqual(img["width"], 5 * 384)

    def test_label_animated_on_its_word(self) -> None:
        # The white label appears at W(1, "world") = 0.75 s: absent at 0.5 s, present at 1.2 s.
        """A label timed with W(1, "world") is absent before 0.75 s and present after it in the rendered video.
        Guards timing.js helpers reaching the GSAP timeline at the voiced word's time."""
        def white_pixels(t: float) -> int:
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(self.scene_mp4), "-frames:v", "1",
                 "-vf", "crop=200:120:140:140,format=gray", "-f", "rawvideo", "-"],
                check=True, capture_output=True,
            ).stdout
            return sum(1 for b in raw if b > 240)

        self.assertLess(white_pixels(0.5), 100)
        self.assertGreater(white_pixels(1.2), 10000)

    def test_meta_after_render(self) -> None:
        """scenes.render writes meta.json with the voice version, which makes the version the latest render.
        Guards assemble picking rendered versions only."""
        self.assertEqual(state.latest_render(self.project, "intro"), self.sdir)
        meta = state.read_meta(self.sdir)
        self.assertEqual(meta["voice_version"], "v1")

    def test_frames_at_given_times(self) -> None:
        """scenes.frames extracts full-size PNGs at the given times from the latest render. Guards the `frames`
        command."""
        paths = scenes.frames(self.project, "intro", [0.5, 1.5])
        self.assertEqual(len(paths), 2)
        img = media.probe(paths[0])["streams"][0]
        self.assertEqual((img["width"], img["height"]), (1920, 1080))

    def test_unknown_word_blocks_render(self) -> None:
        """scenes.scaffold copies index.html from the previous version, and scenes.render refuses a helper call
        naming a word not in the narration. Guards the static helper check before rendering."""
        sdir = scenes.scaffold(self.project, self.scene, NODE_DIR)
        self.assertEqual(sdir.name, "v2")
        html = (sdir / "index.html").read_text()
        self.assertIn('W(1, "world")', html)  # copied from v1
        (sdir / "index.html").write_text(html.replace('W(1, "world")', 'W(1, "planet")'))
        with self.assertRaises(scenes.SceneError) as cm:
            scenes.render(self.project, self.scene, NODE_DIR)
        self.assertIn("planet", str(cm.exception))
        shutil.rmtree(sdir)


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestRenderEndTemplate(unittest.TestCase):
    """An end scene: generated page, no image, credit held past the narration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "end_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        (p / "storyboard.md").write_text(
            "# End test\n\nTopic: Rendering.\n\n## end\n\nTemplate: end\n\n"
            "| Narration | On screen |\n|---|---|\n| Hello world. | Hello takeaway |\n",
            encoding="utf-8",
        )
        (p / "settings.yaml").write_text("author: [Jane Doe]\n", encoding="utf-8")
        settings.use_project(p)
        data = storyboard.load(p)
        cls.scene = data["scenes"][0]
        vdir = versions.next_version(state.voice_root(p, "end"))
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={DURATION}",
                str(vdir / "narration.wav"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        state.write_meta(vdir, {"duration": DURATION})
        cls.sdir = scenes.scaffold(p, cls.scene, NODE_DIR)
        cls.scene_mp4 = scenes.render(p, cls.scene, NODE_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def test_starting_page_and_card_without_image(self) -> None:
        """scenes.scaffold of an end template writes the suggested end page and card.js with the beats and
        author, and no background image. Guards template scenes without Image."""
        self.assertIn("SUGGESTED end scene", (self.sdir / "index.html").read_text())
        card = (self.sdir / scenes.CARD_JS).read_text()
        self.assertIn("Hello takeaway", card)
        self.assertIn("Jane Doe", card)
        self.assertFalse((self.sdir / scenes.BACKGROUND).exists())

    def test_rescaffold_keeps_restyled_page_and_refreshes_text(self) -> None:
        """scenes.scaffold keeps a restyled index.html and rewrites card.js from the storyboard. Guards text
        edits reaching a restyled card."""
        html = (self.sdir / "index.html").read_text().replace("#0b1320", "#ffffff")
        (self.sdir / "index.html").write_text(html)
        scene = dict(self.scene, beats=["New takeaway"])
        sdir = scenes.scaffold(self.project, scene, NODE_DIR)
        try:
            self.assertIn("#ffffff", (sdir / "index.html").read_text())
            self.assertIn("New takeaway", (sdir / scenes.CARD_JS).read_text())
        finally:
            shutil.rmtree(sdir)
            (self.sdir / "index.html").write_text(html.replace("#ffffff", "#0b1320"))

    def test_length_includes_credit_hold(self) -> None:
        """scenes.render of an end scene lasts the narration plus the template's hold_seconds. Guards the credit
        being held past the narration."""
        self.assertAlmostEqual(media.duration(self.scene_mp4), DURATION + scenes.hold_seconds(self.scene), delta=0.05)


BAR = """<div id="bar" style="position:absolute;left:200px;top:400px;width:1200px;height:200px;
    background:#fff;transform-origin:0 50%;transform:scaleX(0)"></div>
    <!-- drawn elements here -->"""
GROW = """const tl = gsap.timeline({ paused: true });
  tl.to("#bar", { scaleX: 1, duration: 0.3 }, W(1, "world"));
  tl.fromTo("#anchored", { scale: 1 }, { scale: 1.1, transformOrigin: "50% 50%", duration: SE(1) - S(1) }, S(1));"""


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestRenderWithoutImage(unittest.TestCase):
    """An HTML scene with a Brief and no Image: everything on screen is drawn in the page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "drawn_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        (p / "storyboard.md").write_text(
            "# Drawn test\n\nTopic: Rendering.\n\n## chart\n\nBrief: A bar grows on its word.\n\n"
            "| Narration | On screen |\n|---|---|\n| Hello world. | bar grows on 'world' |\n",
            encoding="utf-8",
        )
        cls.scene = storyboard.load(p)["scenes"][0]
        assert "image" not in cls.scene
        vdir = versions.next_version(state.voice_root(p, "chart"))
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={DURATION}",
                str(vdir / "narration.wav"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        state.write_meta(vdir, {"duration": DURATION})
        cls.sdir = scenes.scaffold(p, cls.scene, NODE_DIR)
        html = (cls.sdir / "index.html").read_text()
        html = html.replace("<!-- drawn elements here -->", BAR)
        html = html.replace("const tl = gsap.timeline({ paused: true });", GROW)
        (cls.sdir / "index.html").write_text(html)
        cls.scene_mp4 = scenes.render(p, cls.scene, NODE_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_rendered_without_background_png(self) -> None:
        """scenes.scaffold and render of a scene without an image give a 2 s, 60-frame scene.mp4 with no
        background.png, and status reports nothing to redo. Guards scenes drawn in the page with no picture."""
        self.assertFalse((self.sdir / scenes.BACKGROUND).exists())
        video = next(s for s in media.probe(self.scene_mp4)["streams"] if s["codec_type"] == "video")
        self.assertEqual(int(video["nb_frames"]), 60)
        self.assertEqual(status.render_reasons(self.project, self.scene), [])

    def test_drawn_bar_on_its_word(self) -> None:
        """The bar drawn in #anchored is absent before W(1, "world") and present after it, over the dark page
        background. Guards the timeline and the camera layer of the drawn starting page."""
        def white_pixels(t: float) -> int:
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(self.scene_mp4), "-frames:v", "1",
                 "-vf", "crop=400:100:600:450,format=gray", "-f", "rawvideo", "-"],
                check=True, capture_output=True,
            ).stdout
            return sum(1 for b in raw if b > 240)

        self.assertLess(white_pixels(0.5), 100)
        self.assertGreater(white_pixels(1.6), 30000)

    def test_frames(self) -> None:
        """scenes.frames extracts frames from the scene without an image. Guards the `frames` command."""
        img = media.probe(scenes.frames(self.project, "chart", [1.0])[0])["streams"][0]
        self.assertEqual((img["width"], img["height"]), (1920, 1080))


if __name__ == "__main__":
    unittest.main()
