"""short_video_tool.video_scene and `Engine: video` in the storyboard: parsing,
validation errors, the fill-to-duration filter, the scaffold of a video scene
(references/video-model.md, references/storyboard.md "Video scenes")."""
import json
import tempfile
import unittest
from pathlib import Path

from short_video_tool import scenes, settings, state, status, storyboard, versions, video_scene
from short_video_tool.engine import Engine

MD = """\
# Video

Topic: Cells.

## swim
Engine: video
Image: a.png
Brief: The cell drifts to the right, the camera follows slowly.

| Narration | On screen |
|---|---|
| The cell moves. | drift |
"""

JSON_SCENE = {"id": "swim", "engine": "video", "image": "a.png", "brief": "Drift.",
              "narration": ["The cell moves."], "beats": ["drift"]}

TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": 3.5, "backend": "kokoro", "voice": "af_heart",
    "speed": 1.0, "sentences": [{"index": 1, "text": "The cell moves.", "start": 0.25, "end": 3.0, "aligned": True,
                                 "words": [{"text": "The", "start": 0.25, "end": 0.4}]}],
}


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


class TestEngine(unittest.TestCase):

    def test_enum(self) -> None:
        """Engine lists the four engines, storyboard.ENGINES follows it, and Engine.of defaults to html.
        Guards one fixed set of engine names."""
        self.assertEqual(storyboard.ENGINES, ("html", "manim", "clip", "video"))
        self.assertEqual(Engine.of({}), Engine.HTML)
        self.assertEqual(Engine.of({"engine": "video"}), Engine.VIDEO)


class TestStoryboard(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads a video scene with its Image and Brief, and is_video tells it from an
        html scene. Guards `Engine: video` in storyboard.md."""
        scene = storyboard.parse_markdown(MD)["scenes"][0]
        self.assertEqual(scene, {"id": "swim", "engine": "video", "image": "a.png",
                                 "brief": "The cell drifts to the right, the camera follows slowly.",
                                 "narration": ["The cell moves."], "beats": ["drift"]})
        self.assertTrue(storyboard.is_video(scene))
        self.assertFalse(storyboard.is_video(dict(scene, engine="html")))

    def test_json(self) -> None:
        """storyboard.parse_json accepts a video scene and refuses one without `image`. Guards the same rules
        in storyboard.json."""
        data = {"title": "T", "topic": "x", "scenes": [JSON_SCENE]}
        self.assertEqual(storyboard.parse_json(json.dumps(data))["scenes"][0]["engine"], "video")
        bad = {"title": "T", "topic": "x", "scenes": [{k: v for k, v in JSON_SCENE.items() if k != "image"}]}
        with self.assertRaisesRegex(storyboard.StoryboardError,
                                    "scene 'swim': missing `image`; a scene with `engine` video animates"):
            storyboard.parse_json(json.dumps(bad))

    def test_errors(self) -> None:
        """storyboard.parse_markdown refuses a video scene without Image, without Brief, or with a Template, and
        a video scene without a table. Guards the rules of references/storyboard.md "Video scenes"."""
        cases = [
            ("Image: a.png\n", "", "scene 'swim': missing `Image:`; an `Engine: video` scene animates that image"),
            ("Brief: The cell drifts to the right, the camera follows slowly.\n", "", "scene 'swim': missing `Brief:`"),
            ("Image: a.png\n", "Template: title\n", "a template scene takes no `Engine:`"),
            ("| Narration | On screen |\n|---|---|\n| The cell moves. | drift |\n", "",
             "scene 'swim': missing the `| Narration | On screen |` table"),
        ]
        for old, new, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _error(MD.replace(old, new, 1)))


class TestFill(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)
        v, e = settings.get()["video"], settings.encode()
        self.size, self.fps, self.pix = (v["width"], v["height"]), v["fps"], e["pixel_format"]

    def test_short_clip_holds_last_frame(self) -> None:
        """video_scene.fill_filter scales and crops to the `video:` frame, sets fps, SAR and pixel format, and
        holds the last frame for the time the scene runs past a shorter clip. Guards a 5 s model clip filling a
        7.25 s scene."""
        w, h = self.size
        self.assertEqual(video_scene.fill_filter(5.0, 7.25),
                         f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={self.fps},"
                         f"setsar=1,format={self.pix},tpad=stop_mode=clone:stop_duration=2.25")

    def test_long_clip_not_padded(self) -> None:
        """video_scene.fill_filter adds no hold when the clip is as long as the scene or longer. Guards padding
        only a short clip."""
        self.assertNotIn("tpad", video_scene.fill_filter(8.0, 7.25))
        self.assertNotIn("tpad", video_scene.fill_filter(7.25, 7.25))

    def test_command_cuts_at_scene_length(self) -> None:
        """video_scene.fill_command cuts the output at the scene length with `-t`, after the fill filter, with
        no audio. Guards a longer model clip setting the scene length."""
        cmd = [str(c) for c in video_scene.fill_command(Path("in.mp4"), Path("out.mp4"), 8.0, 7.25)]
        self.assertEqual(cmd[cmd.index("-t") + 1], "7.25")
        self.assertEqual(cmd[cmd.index("-vf") + 1], video_scene.fill_filter(8.0, 7.25))
        self.assertIn("-an", cmd)
        self.assertEqual(cmd[-1], "out.mp4")


class TestScaffold(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name)
        (p / "images").mkdir()
        (p / "images" / "a.png").write_bytes(b"png")
        vdir = versions.next_version(state.voice_root(p, "swim"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        (vdir / "narration.wav").write_bytes(b"")
        state.write_meta(vdir, {"duration": TIMING["duration"]})
        settings.use_project(None)
        self.scene = storyboard.parse_markdown(MD)["scenes"][0]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scaffold_files(self) -> None:
        """video_scene.scaffold writes prompt.txt (the Brief), background.png, brief.md, timing.json and
        voice_version into scenes/<id>/v1, and status finds the version's brief.md current. Guards the video
        scene version layout."""
        out = video_scene.scaffold(self.project, self.scene)
        self.assertEqual(out, self.project / "scenes" / "swim" / "v1")
        self.assertEqual(sorted(f.name for f in out.iterdir()),
                         ["background.png", "brief.md", "prompt.txt", "timing.json", "voice_version"])
        self.assertEqual((out / "prompt.txt").read_text(), self.scene["brief"] + "\n")
        self.assertEqual((out / scenes.BACKGROUND).read_bytes(), b"png")
        brief = (out / "brief.md").read_text()
        self.assertIn("## Video model", brief)
        self.assertIn("references/video-model.md", brief)
        self.assertEqual((out / "brief.md").read_text(),
                         status.BRIEFS[Engine.VIDEO](self.scene, TIMING, "v1"))

    def test_rescaffold_keeps_prompt(self) -> None:
        """video_scene.scaffold copies the edited prompt.txt from the latest version. Guards a re-scaffold losing
        the agent's prompt."""
        first = video_scene.scaffold(self.project, self.scene)
        (first / "prompt.txt").write_text("Slow push in.\n")
        second = video_scene.scaffold(self.project, self.scene)
        self.assertEqual((second / "prompt.txt").read_text(), "Slow push in.\n")

    def test_refusals(self) -> None:
        """video_scene.scaffold refuses a non-video scene, a scene without voice and a missing image, and
        video_scene.render refuses a scene never scaffolded or with an empty prompt, before any model call.
        Guards the order scaffold, then render."""
        with self.assertRaisesRegex(scenes.SceneError, "not a video scene"):
            video_scene.scaffold(self.project, {"id": "swim", "image": "a.png"})
        with self.assertRaisesRegex(scenes.SceneError, "no voice yet"):
            video_scene.scaffold(self.project, dict(self.scene, id="other"))
        with self.assertRaisesRegex(scenes.SceneError, "nothing.png not found"):
            video_scene.scaffold(self.project, dict(self.scene, image="nothing.png"))
        with self.assertRaisesRegex(scenes.SceneError, "run `scaffold` first"):
            video_scene.render(self.project, self.scene)
        out = video_scene.scaffold(self.project, self.scene)
        (out / "prompt.txt").write_text(" \n")
        with self.assertRaisesRegex(scenes.SceneError, "prompt.txt is empty"):
            video_scene.render(self.project, self.scene)
