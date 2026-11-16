"""`refs` on a video and an image made with FFmpeg lavfi: frames at a fixed
rate and at scene changes, contact sheets, palettes, the motion curve and
refs.json (references/reference-video.md, step 1)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from short_video_tool import refs
from tests.prereq import requires

FFMPEG = shutil.which("ffmpeg") is not None


def _lavfi(out: Path, src: str, *args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, *args, str(out)], check=True)


@requires(FFMPEG, "ffmpeg on PATH")
class RefsRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        src = cls.tmp / "src"
        src.mkdir()
        # 2 s red, then 2 s blue: one scene change at 2.0 s
        cls.video = src / "clip.mp4"
        _lavfi(cls.video, "color=c=red:s=320x180:r=24:d=2[a];color=c=blue:s=320x180:r=24:d=2[b];[a][b]concat=n=2",
               "-pix_fmt", "yuv420p")
        _lavfi(src / "green.png", "color=c=green:s=200x100", "-frames:v", "1")
        cls.out = cls.tmp / "refs"
        cls.index = refs.run(cls.video, cls.out, fps=4)
        cls.index = refs.run(src / "green.png", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_video_entry(self):
        """A video gives its size, fps, duration, the scene change at 2 s, 4 frames per second
        with times in their names, sheets of 12, sampled colours and a motion peak at the cut."""
        v = next(e for e in self.index["sources"] if e["kind"] == "video")
        self.assertEqual((v["width"], v["height"], v["fps"]), (320, 180, 24.0))
        self.assertAlmostEqual(v["duration"], 4.0, delta=0.05)
        self.assertEqual(len(v["cuts"]), 1)
        self.assertAlmostEqual(v["cuts"][0], 2.0, delta=0.05)
        rate = [f for f in v["frames"] if f["kind"] == "rate"]
        self.assertEqual(len(rate), 16)
        self.assertEqual(rate[1]["file"], "t000.250.png")
        for f in v["frames"]:
            self.assertTrue((self.out / "clip" / f["file"]).is_file(), f["file"])
        # 17 frames: two sheets of 12 and 5
        self.assertEqual([len(s["frames"]) for s in v["sheets"]], [12, 5])
        self.assertEqual(v["sheets"][0]["palette"][0]["hex"][:2], "#f")  # red dominates the first 3 s
        self.assertEqual(rate[0]["median"][:2], "#f")
        motion = np.array(v["motion"]["values"])
        self.assertAlmostEqual(motion[motion[:, 1].argmax(), 0], 2.0, delta=0.1)
        self.assertGreater(motion[:, 1].max(), 0.1)

    def test_images_and_index(self):
        """Images are copied and sheeted, and a second source is added to refs.json beside the first."""
        saved = json.loads((self.out / refs.INDEX).read_text())
        self.assertEqual([e["dir"] for e in saved["sources"]], ["clip", "images"])
        img = saved["sources"][1]
        self.assertEqual(img["images"][0]["width"], 200)
        self.assertTrue((self.out / "images" / "green.png").is_file())
        self.assertTrue((self.out / "images" / "sheet_01.png").is_file())
        self.assertEqual(img["palette"][0]["share"], 1.0)
        r, g, b = (int(img["palette"][0]["hex"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(r < 10 and b < 10 and 120 < g < 135, img["palette"][0]["hex"])  # lavfi green, #008000

    def test_rerun_replaces_entry(self):
        """A second run on the same video replaces its entry and its frames."""
        out = self.tmp / "again"
        refs.run(self.video, out, fps=1)
        idx = refs.run(self.video, out, fps=2)
        self.assertEqual(len(idx["sources"]), 1)
        self.assertEqual(sum(f["kind"] == "rate" for f in idx["sources"][0]["frames"]), 8)
        self.assertTrue((out / "clip" / "t000.500.png").is_file())

    def test_missing_source(self):
        """A missing source raises RefsError."""
        with self.assertRaises(refs.RefsError):
            refs.run(self.tmp / "nothing.mp4", self.tmp / "x")


if __name__ == "__main__":
    unittest.main()
