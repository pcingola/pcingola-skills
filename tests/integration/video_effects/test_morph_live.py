"""`keys` without --end, every keyframe generated with `image-gen generate`
and the `image_edit` model of tests/config.yaml, then `morph --from` of
video-effects. Each CLI runs as `python -m` in a child process of the root
`dev` environment (the working tree's lib/), with the user's settings file
hidden and TEST_CONFIG in SKILLS_CONFIG."""

import json
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG
from tests.subproc import child_env, run_module

VIDEO_EFFECTS = "video_effects_tool"
IMAGE_GEN = "image_gen_tool"
# The CLIs' environment: no user settings file, the tiny models of tests/config.yaml.
ENV = child_env(SKILLS_CONFIG=str(TEST_CONFIG))
STYLE = "soft watercolour painting on textured paper, gentle washes of colour, visible brush strokes"


def drawing(path: Path) -> Path:
    """A flat drawing: sky, ground, a house with a door and window, a sun, a tree."""
    img = np.zeros((432, 768, 3), np.uint8)
    img[:] = (235, 200, 140)
    img[300:] = (90, 170, 110)
    cv2.circle(img, (640, 90), 45, (60, 210, 250), -1)
    cv2.rectangle(img, (220, 190), (420, 330), (70, 110, 200), -1)
    cv2.fillPoly(img, [np.array([(200, 190), (320, 110), (440, 190)])], (50, 60, 140))
    cv2.rectangle(img, (300, 250), (340, 330), (40, 70, 110), -1)
    cv2.rectangle(img, (240, 215), (280, 250), (240, 230, 200), -1)
    cv2.rectangle(img, (555, 220), (575, 330), (40, 80, 110), -1)
    cv2.circle(img, (565, 200), 50, (60, 140, 70), -1)
    cv2.imwrite(str(path), img)
    return path


def run(module: str, *argv: str | Path) -> subprocess.CompletedProcess:
    """`python -m <module> <argv>` in ENV, for at most 25 s (below the 30 s test timeout)."""
    return run_module(module, [str(a) for a in argv], ENV)


def generate(entry: dict) -> subprocess.CompletedProcess:
    refs = [a for r in entry["refs"] for a in ("--ref", r)]
    model = ["--model", entry["model"]] if entry["model"] else []
    return run(IMAGE_GEN, "generate", "--prompt", entry["prompt"], *refs, "--out", entry["out"], *model,
               "--aspect", entry["aspect"], "--size", "1K", "--quality", "low")


@requires(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class TestMorphLive(unittest.TestCase):
    def test_keys_generate_morph(self) -> None:
        """keys with one in-between, then image-gen for every listed keyframe with the image_edit model of
        tests/config.yaml, then morph --from: size, fps, frame count, strip and sidecar inputs equal to the chain. Guards that keys.json
        entries are valid image-gen arguments and that generated keys render."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            start = drawing(tmp / "start.png")
            keys_dir = tmp / "keys"
            r = run(VIDEO_EFFECTS, "keys", start, "--style", STYLE, "--dir", keys_dir, "--fractions", "0.5")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads((keys_dir / "keys.json").read_text())
            self.assertEqual([e["name"] for e in data["images"]], ["end", "k50"])

            # the end image first (the in-betweens reference it), then the in-betweens in parallel
            end, betweens = data["images"][0], data["images"][1:]
            r = generate(end)
            self.assertEqual(r.returncode, 0, r.stderr)
            with ThreadPoolExecutor(len(betweens)) as pool:
                for e, r in zip(betweens, pool.map(generate, betweens)):
                    self.assertEqual(r.returncode, 0, f"{e['name']}: {r.stderr}")
            for e in data["images"]:
                self.assertTrue(Path(e["out"]).is_file(), e["out"])

            out = tmp / "morph.mp4"
            r = run(VIDEO_EFFECTS, "morph", "--from", keys_dir, "--out", out, "--trans", "1.5", "--hold", "0.5",
                    "--size", "640x360", "--fps", "24")
            self.assertEqual(r.returncode, 0, r.stderr)
            probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json",
                                    str(out)], capture_output=True, text=True, check=True).stdout
            info = json.loads(probe)["streams"][0]
            self.assertEqual((info["width"], info["height"]), (640, 360))
            self.assertEqual(info["r_frame_rate"], "24/1")
            self.assertEqual(int(info["nb_read_frames"]), 36 + 12 + 12)
            strip = cv2.imread(str(tmp / "morph_frames.png"))
            self.assertEqual(strip.shape, (720, 1920, 3))
            side = json.loads((tmp / "morph.mp4.json").read_text())
            self.assertEqual(side["effect"], "morph")
            self.assertEqual([i["path"] for i in side["inputs"]], data["chain"])
            self.assertEqual(side["frames"]["total"], 60)
