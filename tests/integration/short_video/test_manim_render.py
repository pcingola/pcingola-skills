"""Integration test for scaffold + render of a manim scene with the real Manim,
and a film assembled from an HTML scene and a manim scene.

The voice versions are made by hand (a tone WAV and its timing.json; the
voiceover skill is not used). The Manim environment
(`config.manim_env()`) is created by uv on first use; the tests fail when it
cannot be.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.prereq import requires
from tests.integration.short_video import wrapper_env
from tests.integration.short_video.wrapper_env import NODE_DIR
from short_video_tool import config, manim_scene, media, mix, scenes, settings, state, storyboard, versions

DURATION = 2.0
TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": DURATION,
    "backend": "kokoro", "voice": "af_heart", "speed": 1.0,
    "sentences": [{
        "index": 1, "text": "Hello world.", "start": 0.25, "end": 1.4, "aligned": True,
        "words": [{"text": "Hello", "start": 0.25, "end": 0.7}, {"text": "world.", "start": 0.75, "end": 1.4}],
    }],
}
# A white square that appears on W(1, "world") = 0.75 s, in the top-left corner.
SCENE_PY = '''from manim import UL, WHITE, FadeIn, Square
from sv_timing import W, SE, TimedScene


class Main(TimedScene):
    def construct(self):
        self.camera.background_color = "#000000"
        box = Square(side_length=2, color=WHITE, fill_opacity=1).to_corner(UL)
        self.at(W(1, "world"))
        self.play(FadeIn(box), run_time=0.1)
        self.at(SE(1))
        self.finish()
'''
STORYBOARD = """# Manim test

Topic: Rendering.

## html
Image: cell.png
Brief: Hold.

| Narration | On screen |
|---|---|
| Hello world. | hold |

## plot
Engine: manim
Brief: A square on "world".

| Narration | On screen |
|---|---|
| Hello world. | square on "world" |
"""


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _manim_ready() -> str | None:
    """None when the Manim environment runs, else the reason it does not."""
    if shutil.which("ffmpeg") is None:
        return "ffmpeg not installed (brew install ffmpeg)"
    if shutil.which("uv") is None:
        return "uv not installed"
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["UV_PROJECT_ENVIRONMENT"] = str(wrapper_env.MANIM_VENV)
    proc = subprocess.run(["uv", "run", "--project", str(config.MANIM_PROJECT), "manim", "--version"],
                          env=env, capture_output=True, text=True, timeout=1200)
    if proc.returncode != 0:
        return "the Manim environment could not be created: " + (proc.stderr or proc.stdout).strip()[-500:]
    return None


def _render(project: Path, sid: str) -> Path:
    """manim_scene.render of scene `sid` through short-video.sh render, which sets PLUGIN_ENV_DIR and so the
    Manim environment; returns the scene.mp4 it prints."""
    r = wrapper_env.run("render", "-p", project, "--scene", sid)
    if r.returncode != 0:
        raise AssertionError(f"short-video.sh render failed ({r.returncode}):\n{r.stderr}")
    return Path(r.stdout.splitlines()[0])


def _render_error(project: Path, sid: str) -> str:
    """The error of a short-video.sh render that must fail (the SceneError message on stderr)."""
    r = wrapper_env.run("render", "-p", project, "--scene", sid)
    if r.returncode == 0:
        raise AssertionError(f"short-video.sh render succeeded: {r.stdout}")
    return r.stderr


def _voice(project: Path, sid: str) -> None:
    vdir = versions.next_version(state.voice_root(project, sid))
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={DURATION}",
            str(vdir / "narration.wav"))
    (vdir / "timing.json").write_text(json.dumps(TIMING))
    state.write_meta(vdir, {"duration": DURATION})


class TestManimRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        reason = _manim_ready()
        if reason:
            raise AssertionError(f"missing prerequisite: {reason}")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "manim_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1200x900", "-frames:v", "1", str(p / "images" / "cell.png"))
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        (p / "settings.yaml").write_text("author: [Jane Doe]\n", encoding="utf-8")
        settings.use_project(p)
        cls.data = storyboard.load(p)
        cls.scene = storyboard.scene_by_id(cls.data, "plot")
        for sid in ("html", "plot"):
            _voice(p, sid)
        cls.sdir = manim_scene.scaffold(p, cls.scene)
        (cls.sdir / "scene.py").write_text(SCENE_PY, encoding="utf-8")
        cls.scene_mp4 = _render(p, "plot")

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def _video(self, path: Path) -> dict:
        return next(s for s in media.probe(path)["streams"] if s["codec_type"] == "video")

    def test_files(self) -> None:
        """manim_scene.render with the real Manim leaves scene.py, sv_timing.py, timing.json, brief.md,
        voice_version, silent.mp4, scene.mp4, a five-tile contact sheet and meta.json in the version. Guards the
        manim scene version layout."""
        self.assertEqual(self.scene_mp4, self.project / "scenes" / "plot" / "v1" / "scene.mp4")
        for name in ("scene.py", "sv_timing.py", "timing.json", "brief.md", "voice_version",
                     "silent.mp4", "scene.mp4", "contact.png", "meta.json"):
            self.assertTrue((self.sdir / name).is_file(), name)
        self.assertEqual(media.probe(self.sdir / "contact.png")["streams"][0]["width"], 5 * 384)

    def test_meta(self) -> None:
        """manim_scene.render writes meta.json with the voice version, engine manim and fps, which makes the
        version the latest render. Guards assemble finding manim scenes."""
        self.assertEqual(state.latest_render(self.project, "plot"), self.sdir)
        meta = state.read_meta(self.sdir)
        self.assertEqual((meta["voice_version"], meta["engine"], meta["fps"]), ("v1", "manim", 30))

    def test_sixty_frames_at_1080p_square_pixels(self) -> None:
        """manim_scene.render of a 2 s scene gives 60 frames at 1920x1080 with SAR 1:1 and muxed narration.
        Guards the h264_metadata SAR fix that concat with HyperFrames scenes needs."""
        video = self._video(self.scene_mp4)
        self.assertEqual(int(video["nb_frames"]), 60)
        self.assertEqual((video["width"], video["height"]), (1920, 1080))
        self.assertEqual(video["sample_aspect_ratio"], "1:1")
        streams = media.probe(self.scene_mp4)["streams"]
        self.assertEqual(sorted(s["codec_type"] for s in streams), ["audio", "video"])
        self.assertAlmostEqual(media.duration(self.scene_mp4), DURATION, delta=0.05)

    def test_square_appears_on_its_word(self) -> None:
        """A square shown with self.at(W(1, "world")) is absent before 0.75 s and present after it in the real
        render. Guards sv_timing's TimedScene.at with real Manim frame counting."""
        def white_pixels(t: float) -> int:
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(self.scene_mp4), "-frames:v", "1",
                 "-vf", "crop=120:120:120:120,format=gray", "-f", "rawvideo", "-"],
                check=True, capture_output=True,
            ).stdout
            return sum(1 for b in raw if b > 240)

        self.assertLess(white_pixels(0.5), 100)
        self.assertGreater(white_pixels(1.2), 10000)

    def test_starting_page_moves(self) -> None:
        """The starting scene.py renders with the real Manim to the narration length, and its frames change
        while the sentence plays and stay still in the last 0.5 s. Guards the moving starting page."""
        sdir = manim_scene.scaffold(self.project, self.scene)
        try:
            (sdir / "scene.py").write_text(manim_scene.render_starting_page(self.scene), encoding="utf-8")
            mp4 = _render(self.project, self.scene["id"])
            self.assertAlmostEqual(media.duration(mp4), DURATION, delta=0.05)

            def frame(t: float) -> bytes:
                return subprocess.run(
                    ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4), "-frames:v", "1",
                     "-vf", "scale=192:108,format=gray", "-f", "rawvideo", "-"],
                    check=True, capture_output=True,
                ).stdout

            def changed(a: float, b: float) -> int:
                return sum(1 for x, y in zip(frame(a), frame(b)) if abs(x - y) > 24)

            self.assertGreater(changed(0.4, 1.0), 200)
            self.assertLess(changed(1.6, 1.9), 20)
        finally:
            shutil.rmtree(sdir)

    def test_unknown_word_blocks_render(self) -> None:
        """manim_scene.scaffold copies scene.py from the latest version, and render refuses a helper call naming
        a word not in the narration. Guards the static check before running Manim."""
        sdir = manim_scene.scaffold(self.project, self.scene)
        try:
            self.assertEqual((sdir / "scene.py").read_text(), SCENE_PY)
            (sdir / "scene.py").write_text(SCENE_PY.replace('W(1, "world")', 'W(1, "planet")'))
            self.assertRegex(_render_error(self.project, "plot"), "planet")
        finally:
            shutil.rmtree(sdir)

    def test_missing_finish_fails_length_check(self) -> None:
        """manim_scene.render refuses a scene that ends short without self.finish(), naming it. Guards the
        length check after the Manim render."""
        sdir = manim_scene.scaffold(self.project, self.scene)
        try:
            (sdir / "scene.py").write_text(SCENE_PY.replace("        self.finish()\n", ""))
            self.assertRegex(_render_error(self.project, "plot"), r"self\.finish\(\)")
        finally:
            shutil.rmtree(sdir)

    @requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
    def test_mixed_film(self) -> None:
        """mix.assemble concatenates an HTML and a manim scene with equal SAR into a film of both lengths.
        Guards mixing the two engines in one film."""
        html_scene = storyboard.scene_by_id(self.data, "html")
        scenes.scaffold(self.project, html_scene, NODE_DIR)
        html_mp4 = scenes.render(self.project, html_scene, NODE_DIR)
        self.assertEqual(self._video(html_mp4)["sample_aspect_ratio"], self._video(self.scene_mp4)["sample_aspect_ratio"])
        film = mix.assemble(self.project, self.data)
        manifest = json.loads((film.parent / "manifest.json").read_text())
        self.assertEqual([s["id"] for s in manifest["scenes"]], ["html", "plot"])
        video = self._video(film)
        self.assertEqual(int(video["nb_frames"]), 120)
        self.assertAlmostEqual(media.duration(film), 2 * DURATION, delta=0.05)


if __name__ == "__main__":
    unittest.main()
