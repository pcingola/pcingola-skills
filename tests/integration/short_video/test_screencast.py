"""Integration test of `short-video.sh screencast` (references/screencast.md of short-video): a shot list of
a 2x recording made with FFmpeg (testsrc, then black frames) and a screenshot written with OpenCV, rendered
into a clip scene's sources/ through the wrapper, checked with ffprobe and imported with `clip`."""
import json
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from tests.integration.short_video.wrapper_env import run
from tests.prereq import requires

W, H, FPS = 320, 180, 30
SHOTS = 1.2 + 1.0 + 0.8

MD = """\
# Screencast film

Topic: A tool in use.

## intro
Image: a.png
Brief: Hold.

| Narration | On screen |
|---|---|
| The tool. | hold |

## demo
Engine: clip
Brief: The tool typing a prompt and pressing a button.
"""

SHOT_LIST = """\
fade: 0.3
shots:
  - video: rec.mp4
    from: 0.2
    to: 1.8
    length: 1.2
    scale: 2
    camera:
      - {t: 0, zoom: 0.8, yaw: 8, pitch: 3}
      - {t: 1.2, rect: [40, 30, 160, 90], yaw: 0, pitch: 0}
    highlights: [{rect: [40, 30, 160, 90], from: 0.2}]
    clicks: [{t: 0.6, at: [120, 75]}]
    caption: Pick a frame
  - image: page.png
    scale: 2
    length: 1.0
    typing: [{rect: [20, 18, 290, 22], from: 0.1, to: 0.8}]
    draw: [{rect: [20, 100, 80, 30], from: 0.2, to: 0.7}]
    labels: [{text: Type the prompt, at: [10, 10], from: 0, to: 1}]
  - video: rec.mp4
    from: 2.0
    to: 2.6
    length: 0.8
"""


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=25)


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True, timeout=25).stdout
    return json.loads(out)


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestScreencast(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "film"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        (p / "settings.yaml").write_text(f"video:\n  width: {W}\n  height: {H}\n  fps: {FPS}\n")
        (p / "storyboard.md").write_text(MD)
        ffmpeg("-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}", "-frames:v", "1", str(p / "images" / "a.png"))
        cls.src = s = Path(cls._tmp.name) / "src"
        s.mkdir()
        # 2 s of test pattern, then 1 s of black (a native dropdown opening), at 2x the 320x180 page
        ffmpeg("-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=1",
               "-filter_complex", "[0][1]concat=n=2:v=1", "-pix_fmt", "yuv420p", str(s / "rec.mp4"))
        img = np.full((360, 640, 3), 240, np.uint8)
        cv2.putText(img, "open the settings", (48, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (30, 30, 30), 2, cv2.LINE_AA)
        cv2.imwrite(str(s / "page.png"), img)
        (s / "shots.yaml").write_text(SHOT_LIST)
        cls.done = run("screencast", "-p", p, "--shots", s / "shots.yaml", "--scene", "demo")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_writes_clip_at_video_settings(self) -> None:
        """`screencast --scene` writes sources/<ID>-screencast.mp4 at the `video:` size and fps, as long as the
        shots, and prints the `clip` step."""
        self.assertEqual(self.done.returncode, 0, self.done.stderr)
        out = self.project / "sources" / "demo-screencast.mp4"
        self.assertIn(f"next: clip --scene demo {out}", self.done.stdout)
        info = probe(out)
        s = info["streams"][0]
        self.assertEqual((s["width"], s["height"]), (W, H))
        self.assertEqual(Fraction(s["r_frame_rate"]), FPS)
        self.assertEqual(int(s["nb_frames"]), round(SHOTS * FPS))
        self.assertAlmostEqual(float(info["format"]["duration"]), SHOTS, delta=1.5 / FPS)

    def test_warns_on_black_recording_frames(self) -> None:
        """The third shot reads the black part of the recording; the command warns about it."""
        self.assertIn("is black at", self.done.stderr)

    def test_clip_imports_the_result(self) -> None:
        """`clip --scene` accepts the screencast as the clip scene's next version."""
        done = run("clip", "-p", self.project, "--scene", "demo", self.project / "sources" / "demo-screencast.mp4")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.project / "scenes" / "demo" / "v1" / "scene.mp4").is_file())

    def test_stills_and_bad_shot_list(self) -> None:
        """`--at` writes PNG frames at the frame size instead of the MP4; an invalid shot list exits 1 with
        the place of the error."""
        out = Path(self._tmp.name) / "stills" / "s.mp4"
        done = run("screencast", "-p", self.project, "--shots", self.src / "shots.yaml", "-o", out, "--at", "0.5,1.35")
        self.assertEqual(done.returncode, 0, done.stderr)
        pngs = sorted(out.parent.glob("s_*.png"))
        self.assertEqual([p.name for p in pngs], ["s_00.500.png", "s_01.350.png"])
        self.assertEqual(cv2.imread(str(pngs[0])).shape, (H, W, 3))
        self.assertFalse(out.exists())
        bad = self.src / "bad.yaml"
        bad.write_text("shots:\n  - image: page.png\n    length: 1\n    camra: []\n")
        done = run("screencast", "-p", self.project, "--shots", bad, "-o", out)
        self.assertEqual(done.returncode, 1)
        self.assertIn("shots[0]: unknown key 'camra'", done.stderr)


if __name__ == "__main__":
    unittest.main()
