"""short_video_tool.presenter_scene and `Engine: presenter` in the storyboard: parsing, validation, the scaffold,
the `status` reasons for a changed picture or recording, and the engine dispatch (references/video-model.md,
"Presenter scenes"; references/storyboard.md "Presenter scenes")."""
import argparse
import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
import unittest
from pathlib import Path

from short_video_tool import cli, presenter_scene, scenes, settings, state, status, storyboard, versions
from short_video_tool.engine import Engine

MD = """\
# Presenter

Topic: Harbours.

## host
Engine: presenter
Image: host.png

| Narration | On screen |
|---|---|
| Welcome to the harbour. | host speaks |
"""

JSON_SCENE = {"id": "host", "engine": "presenter", "image": "host.png", "narration": ["Welcome to the harbour."],
              "beats": ["host speaks"]}

TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": 2.5, "model": "kokoro:kokoro-v1.0", "voice": "af_heart",
    "speed": 1.0, "sentences": [{"index": 1, "text": "Welcome to the harbour.", "start": 0.25, "end": 2.2,
                                 "aligned": True, "words": [{"text": "Welcome", "start": 0.25, "end": 0.6}]}],
}


class TestStoryboard(unittest.TestCase):

    def test_parse_without_brief(self) -> None:
        """parse_markdown reads a presenter scene with `Image:` and no `Brief:` (the brief is optional), and
        is_presenter and Engine.of tell it from a video scene. Guards `Engine: presenter` in storyboard.md."""
        scene = storyboard.parse_markdown(MD)["scenes"][0]
        self.assertEqual(scene, JSON_SCENE)
        self.assertTrue(storyboard.is_presenter(scene))
        self.assertFalse(storyboard.is_video(scene))
        self.assertEqual(Engine.of(scene), Engine.PRESENTER)

    def test_brief_is_kept(self) -> None:
        """A presenter scene's `Brief:` is parsed into `brief` (the model's prompt). Guards a brief dropped
        for the presenter engine."""
        text = MD.replace("Image: host.png\n", "Image: host.png\nBrief: She smiles and opens her hands.\n")
        self.assertEqual(storyboard.parse_markdown(text)["scenes"][0]["brief"], "She smiles and opens her hands.")

    def test_needs_image_in_both_formats(self) -> None:
        """A presenter scene without `image` is refused in storyboard.md and storyboard.json, and so is
        `ambience` (only a video scene has a model sound track). Guards the presenter rules of the shared check."""
        with self.assertRaisesRegex(storyboard.StoryboardError, "missing `Image:`; an `Engine: presenter` scene"):
            storyboard.parse_markdown(MD.replace("Image: host.png\n", ""))
        bad = {"title": "T", "topic": "x", "scenes": [{k: v for k, v in JSON_SCENE.items() if k != "image"}]}
        with self.assertRaisesRegex(storyboard.StoryboardError, "missing `image`; a scene with `engine` presenter"):
            storyboard.parse_json(json.dumps(bad))
        amb = {"title": "T", "topic": "x", "scenes": [dict(JSON_SCENE, ambience=False)]}
        with self.assertRaisesRegex(storyboard.StoryboardError, "only a scene with `engine` video has `ambience`"):
            storyboard.parse_json(json.dumps(amb))


class TestScaffoldAndStatus(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name)
        (p / "images").mkdir()
        (p / "images" / "host.png").write_bytes(b"png")
        self.voice = vdir = versions.next_version(state.voice_root(p, "host"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        (vdir / "narration.wav").write_bytes(b"speech one")
        state.write_meta(vdir, {"duration": TIMING["duration"]})
        settings.use_project(None)
        self.scene = storyboard.parse_markdown(MD)["scenes"][0]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _rendered(self) -> Path:
        """A scaffolded version with the meta.json `render` writes (without the model call)."""
        out = presenter_scene.scaffold(self.project, self.scene)
        state.write_meta(out, {"scene": "host", "voice_version": "v1", "engine": Engine.PRESENTER,
                               "speech_sha256": presenter_scene.speech_digest(self.voice / "narration.wav")})
        return out

    def test_scaffold_files(self) -> None:
        """scaffold writes background.png (the picture), brief.md (with the presenter section), timing.json and
        voice_version, and status finds a render of it current. Guards the presenter scene version layout."""
        out = self._rendered()
        self.assertEqual(sorted(f.name for f in out.iterdir()),
                         ["background.png", "brief.md", "meta.json", "timing.json", "voice_version"])
        self.assertEqual((out / scenes.BACKGROUND).read_bytes(), b"png")
        self.assertIn("## Presenter model", (out / "brief.md").read_text())
        self.assertEqual(status.render_reasons(self.project, self.scene), [])

    def test_status_sees_a_new_picture(self) -> None:
        """A changed picture makes a rendered presenter scene stale. Guards a presenter that keeps an old face."""
        self._rendered()
        (self.project / "images" / "host.png").write_bytes(b"other png")
        self.assertEqual(status.render_reasons(self.project, self.scene),
                         ["the image host.png differs from the one rendered"])

    def test_status_sees_a_new_recording(self) -> None:
        """A changed narration recording (same voice version) and a new voice version each make a rendered
        presenter scene stale: the clip's lips follow the recording. Guards a presenter speaking an old take."""
        self._rendered()
        (self.voice / "narration.wav").write_bytes(b"speech two")
        self.assertEqual(status.render_reasons(self.project, self.scene),
                         ["the recording v1/narration.wav differs from the one the presenter spoke"])
        v2 = versions.next_version(state.voice_root(self.project, "host"))
        (v2 / "timing.json").write_text(json.dumps(TIMING))
        (v2 / "narration.wav").write_bytes(b"speech three")
        state.write_meta(v2, {"duration": TIMING["duration"]})
        self.assertIn("rendered with voice v1, the latest voice version is v2",
                      status.render_reasons(self.project, self.scene))

    def test_status_sees_an_engine_change(self) -> None:
        """A scene switched from presenter to video needs a new render. Guards the engine in meta.json."""
        self._rendered()
        video = dict(self.scene, engine="video", brief="Drift.")
        self.assertEqual(status.render_reasons(self.project, video),
                         ["rendered as engine presenter, the storyboard has video"])

    def test_refusals(self) -> None:
        """scaffold refuses a scene of another engine, a scene without voice and a missing picture; render
        refuses a scene never scaffolded, before any model call. Guards the order scaffold, then render."""
        with self.assertRaisesRegex(scenes.SceneError, "not a presenter scene"):
            presenter_scene.scaffold(self.project, dict(self.scene, engine="video"))
        with self.assertRaisesRegex(scenes.SceneError, "no voice yet"):
            presenter_scene.scaffold(self.project, dict(self.scene, id="other"))
        with self.assertRaisesRegex(scenes.SceneError, "nothing.png not found"):
            presenter_scene.scaffold(self.project, dict(self.scene, image="nothing.png"))
        with self.assertRaisesRegex(scenes.SceneError, "run `scaffold` first"):
            presenter_scene.render(self.project, self.scene)

    def test_cli_dispatches_to_the_presenter_engine(self) -> None:
        """cli scaffold of a presenter scene writes the presenter version (brief.md with the presenter section, no
        index.html or prompt.txt), and cli render sends it to presenter_scene, which refuses an unscaffolded scene
        instead of HyperFrames. Guards the engine choice of the scaffold and render commands."""
        (self.project / "storyboard.md").write_text(MD, encoding="utf-8")

        def run(func, **kw) -> tuple[str, str]:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    func(argparse.Namespace(project=str(self.project), **kw))
                except SystemExit:
                    pass
            return out.getvalue(), err.getvalue()

        _, err = run(cli._cmd_render, scene="host", seed=None)
        self.assertIn("no presenter scene to render; run `scaffold` first", err)
        out, _ = run(cli._cmd_scaffold, scene="host")
        self.assertTrue(out.strip().endswith("scenes/host/v1/brief.md"))
        v1 = self.project / "scenes" / "host" / "v1"
        self.assertIn("## Presenter model", (v1 / "brief.md").read_text())
        self.assertFalse((v1 / "index.html").exists() or (v1 / "prompt.txt").exists())


class TestFit(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_presenter_clip_is_contained(self) -> None:
        """A presenter clip is fitted into the `video:` frame uncropped (`Fit.CONTAIN`): the clip scaled to fit
        inside, over a blurred copy scaled to cover and cropped, then the common tail; a video clip still covers.
        Guards a portrait bucket losing the head to a cover crop in a 16:9 film."""
        from short_video_tool import video_scene
        from short_video_tool.fit import Fit

        v = settings.get()["video"]
        w, h = v["width"], v["height"]
        self.assertEqual(presenter_scene.FIT, Fit.CONTAIN)
        vf = video_scene.fill_filter(5.0, 5.0, presenter_scene.FIT)
        cover = video_scene.fill_filter(5.0, 5.0)
        self.assertTrue(vf.startswith("split[bg][fg];"))
        self.assertIn(f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=", vf)
        self.assertIn(f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fg]", vf)
        self.assertIn("[bg][fg]overlay=(W-w)/2:(H-h)/2,", vf)
        self.assertTrue(vf.endswith(cover.split(f"crop={w}:{h},", 1)[1]))
        self.assertNotIn("split", cover)

    def test_contain_filter_runs(self) -> None:
        """FFmpeg accepts the `Fit.CONTAIN` filter and writes a clip at the `video:` frame size from a portrait
        clip. Guards a filter graph that `-vf` refuses."""
        import subprocess

        from short_video_tool import media, video_scene

        v = settings.get()["video"]
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "in.mp4", Path(tmp) / "out.mp4"
            subprocess.run([media.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                            "testsrc=size=64x96:rate=25:duration=0.4", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                            src],
                           check=True, timeout=25)
            video_scene.fill(src, dest, 0.4, presenter_scene.FIT)
            out = subprocess.run([media.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                                  "stream=width,height", "-of", "csv=p=0", dest],
                                 capture_output=True, text=True, check=True, timeout=25).stdout.strip()
        self.assertEqual(out, f"{v['width']},{v['height']}")
