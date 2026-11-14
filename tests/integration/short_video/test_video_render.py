"""Integration tests of `Engine: video` scenes (references/video-model.md):
`video_scene.fill` with the real FFmpeg, and scaffold + render of a video
scene with the real `ai_models.video.animate` and the `video` model of the
user's ai_models config (a real model call).

The voice version is made by hand (a tone WAV and its timing.json; the
voiceover skill is not used).
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.prereq import requires
from short_video_tool import media, settings, state, storyboard, versions, video_scene

DURATION = 3.0
TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": DURATION,
    "backend": "kokoro", "voice": "af_heart", "speed": 1.0,
    "sentences": [{"index": 1, "text": "A red ball rolls.", "start": 0.25, "end": 2.6, "aligned": True,
                   "words": [{"text": "A", "start": 0.25, "end": 0.35}]}],
}
STORYBOARD = """# Video test

Topic: Rendering.

## ball
Engine: video
Image: ball.png
Brief: The red ball rolls slowly from left to right across the table.

| Narration | On screen |
|---|---|
| A red ball rolls. | ball rolls |
"""
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _video(path: Path) -> dict:
    return next(s for s in media.probe(path)["streams"] if s["codec_type"] == "video")


@requires(HAS_FFMPEG, "ffmpeg and ffprobe not installed")
class TestFill(unittest.TestCase):
    """video_scene.fill on test clips at another size and fps than `video:`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        settings.use_project(None)
        self.v = settings.get()["video"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clip(self, seconds: float) -> Path:
        src = self.dir / f"clip{seconds}.mp4"
        _ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=640x480:rate=24:duration={seconds}", "-pix_fmt", "yuv420p",
                str(src))
        return src

    def _check(self, out: Path, seconds: float) -> None:
        s = _video(out)
        self.assertEqual((int(s["width"]), int(s["height"])), (self.v["width"], self.v["height"]))
        self.assertEqual(s.get("sample_aspect_ratio", "1:1"), "1:1")
        self.assertAlmostEqual(media.video_duration(out), seconds, delta=1.5 / self.v["fps"])

    def test_short_clip_held_to_scene_length(self) -> None:
        """video_scene.fill makes a 1.5 s clip a 3 s scene video at the `video:` size and fps by holding its last
        frame. Guards a model clip shorter than the narration."""
        out = self.dir / "short.mp4"
        self.assertAlmostEqual(video_scene.fill(self._clip(1.5), out, 3.0), 1.5, delta=0.05)
        self._check(out, 3.0)

    def test_long_clip_cut_at_scene_length(self) -> None:
        """video_scene.fill cuts a 4 s clip at a 2.5 s scene length. Guards a model clip longer than the
        narration."""
        out = self.dir / "long.mp4"
        video_scene.fill(self._clip(4.0), out, 2.5)
        self._check(out, 2.5)


@requires(HAS_FFMPEG, "ffmpeg and ffprobe not installed")
class TestVideoRender(unittest.TestCase):
    """scaffold + render of a video scene with the real video model."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "video_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        (p / "settings.yaml").write_text("author: [Jane Doe]\nvideo: {width: 640, height: 360, fps: 24}\n",
                                         encoding="utf-8")
        settings.use_project(p)
        _ffmpeg("-f", "lavfi", "-i", "color=c=white:size=640x360", "-vf",
                "drawbox=x=40:y=130:w=100:h=100:color=red:t=fill", "-frames:v", "1", str(p / "images" / "ball.png"))
        vdir = versions.next_version(state.voice_root(p, "ball"))
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={DURATION}",
                str(vdir / "narration.wav"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        state.write_meta(vdir, {"duration": DURATION})
        cls.scene = storyboard.scene_by_id(storyboard.load(p), "ball")
        video_scene.scaffold(p, cls.scene)
        cls.scene_mp4 = video_scene.render(p, cls.scene, seed=1)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def test_scene_video(self) -> None:
        """video_scene.render writes scene.mp4 at the `video:` size, as long as the narration, with the model's
        clip kept as model.mp4. Guards a video scene assembling like any rendered scene."""
        s = _video(self.scene_mp4)
        self.assertEqual((int(s["width"]), int(s["height"])), (640, 360))
        self.assertAlmostEqual(media.duration(self.scene_mp4), DURATION, delta=0.1)
        self.assertTrue((self.scene_mp4.parent / video_scene.MODEL_MP4).is_file())
        self.assertTrue((self.scene_mp4.parent / "contact.png").is_file())

    def test_meta(self) -> None:
        """video_scene.render records engine video, the voice version, the model, the prompt, the seed and the
        model clip's length in meta.json. Guards `status` and later renders reading the video scene's meta."""
        meta = state.read_meta(self.scene_mp4.parent)
        self.assertEqual((meta["engine"], meta["voice_version"], meta["seed"]), ("video", "v1", 1))
        self.assertEqual(meta["prompt"], self.scene["brief"])
        self.assertTrue(meta["model"])
        self.assertGreater(meta["clip_duration"], 0)
