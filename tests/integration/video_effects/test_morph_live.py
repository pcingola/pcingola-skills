"""`keys` without --end, every keyframe generated with image-gen's `write_images` and the `image_edit` model of
tests/config.yaml, then the morph of `keys.json`'s chain. Everything runs in process under TEST_CONFIG
(`use_settings`)."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from image_gen_tool import models as image_models
from image_gen_tool.generate import write_images
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG, use_settings
from video_effects_tool import cli, keys

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


def generate(entry: dict) -> list[Path]:
    """Generate the keyframe of one keys.json entry with image-gen's `write_images` at size 1K and quality low (the
    entry's prompt, references, model and aspect), written to the entry's `out`; return the written paths."""
    return write_images(entry["prompt"], entry["out"], refs=entry["refs"], aspect_ratio=entry["aspect"],
                        image_size="1K", model=entry["model"], quality="low")


@requires(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class TestMorphLive(unittest.TestCase):
    def test_keys_generate_morph(self) -> None:
        """keys.plan and keys.write with one in-between, then image-gen's write_images for every listed keyframe with
        the image_edit model of tests/config.yaml, then cli.morph of the keys.json chain: size, fps, frame count, strip
        and sidecar inputs equal to the chain. Guards that keys.json entries are valid image-gen arguments (aspect,
        size and tier among image-gen's choices) and that generated keys render."""
        with tempfile.TemporaryDirectory() as tmp, use_settings(TEST_CONFIG):
            tmp = Path(tmp)
            start = drawing(tmp / "start.png")
            keys_dir = tmp / "keys"
            data = keys.plan(start, STYLE, keys_dir, fractions=keys.parse_fractions("0.5"))
            keys.write(data, keys_dir.resolve(), force=False)
            data = json.loads((keys_dir / "keys.json").read_text())
            self.assertEqual([e["name"] for e in data["images"]], ["end", "k50"])

            # the end image first (the in-betweens reference it), then the in-betweens
            for e in data["images"]:
                self.assertIn(e["aspect"], image_models.ASPECT_RATIOS, e["name"])
                self.assertIn(e["size"], image_models.IMAGE_SIZES, e["name"])
                self.assertIn(e["tier"], image_models.TIERS, e["name"])
                self.assertEqual(generate(e), [Path(e["out"])], e["name"])
            for e in data["images"]:
                self.assertTrue(Path(e["out"]).is_file(), e["out"])

            out = tmp / "morph.mp4"
            paths, times = cli.key_chain(from_dir=keys_dir)
            clip = cli.make_clip("640x360", fps=24, trans=1.5, hold=0.5, push_in=0.08)
            cli.morph(paths, times, clip, out)
            probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json",
                                    str(out)], capture_output=True, text=True, check=True, timeout=25).stdout
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
