"""Effects through the CLI: sidecar, strip, frame counts, refusals."""

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import cv2

from video_effects_tool.cli import main

from video_effects_tool import keys

from .images import gradient, save, texture, with_disc
from tests.prereq import requires

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
SMALL = ["--size", "96x54", "--fps", "10", "--trans", "1", "--hold", "0.5"]


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            main(list(argv))
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_frames,codec_name,pix_fmt", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.a = save(self.dir / "a.png", with_disc(texture(160, 90), 50, 45, 6))
        self.b = save(self.dir / "b.png", with_disc(texture(160, 90), 70, 45, 6))
        self.mid = save(self.dir / "m.png", with_disc(texture(160, 90), 60, 45, 6))

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestRefusals(Base):
    def test_missing_file(self) -> None:
        """cli crossfade with a missing input exits 1 with 'no such file'. Guards frames.load_image's check
        before OpenCV returns None."""
        code, _, err = run("crossfade", str(self.a), str(self.dir / "nope.png"), "--out", str(self.dir / "x.mp4"),
                           *SMALL)
        self.assertEqual(code, 1)
        self.assertIn("no such file", err)

    def test_unreadable(self) -> None:
        """cli morph with a file OpenCV cannot decode exits 1 with 'cannot read'. Guards the None check after
        cv2.imread."""
        bad = self.dir / "bad.png"
        bad.write_bytes(b"garbage")
        code, _, err = run("morph", "--keys", str(self.a), str(bad), "--out", str(self.dir / "x.mp4"), *SMALL)
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)

    def test_one_key(self) -> None:
        """cli morph with one key exits 1 with 'at least 2'. Guards render's key count check before FlowChain."""
        code, _, err = run("morph", "--keys", str(self.a), "--out", str(self.dir / "x.mp4"), *SMALL)
        self.assertEqual(code, 1)
        self.assertIn("at least 2", err)

    def test_bad_options(self) -> None:
        """cli refuses a bad size, zero transformation, negative fps and hold, and region --spread 1 with one
        error line. Guards the option checks reaching the user as 'error:', not a traceback."""
        out = str(self.dir / "x.mp4")
        for extra in (["--size", "100x"], ["--trans", "0"], ["--fps", "-1"], ["--hold", "-1"]):
            code, _, err = run("crossfade", str(self.a), str(self.b), "--out", out, *SMALL, *extra)
            self.assertEqual(code, 1, extra)
            self.assertTrue(err.startswith("error:"), err)
        code, _, err = run("region", "--keys", str(self.a), str(self.b), "--out", out, *SMALL, "--spread", "1")
        self.assertEqual(code, 1)

    def test_more_refusals(self) -> None:
        """cli refuses negative --seed, --steps outside [2, 480], --push-in above 0.5, a side above 7680 and a
        non-image strip suffix, and writes no output. Guards every option being checked before rendering."""
        out = str(self.dir / "x.mp4")
        two = ["--keys", str(self.a), str(self.b), "--out", out, *SMALL]
        cases = [
            ("region", *two, "--seed", "-1"),
            ("region", *two, "--steps", "1"),
            ("region", *two, "--steps", "481"),
            ("morph", *two, "--push-in", "0.6"),
            ("morph", *two, "--size", "7682x100"),
            ("morph", *two, "--strip", str(self.dir / "s.gif")),
        ]
        for argv in cases:
            code, _, err = run(*argv)
            self.assertEqual(code, 1, argv)
            self.assertTrue(err.startswith("error:"), err)
        self.assertFalse(Path(out).exists())

    def test_from_without_keys_json(self) -> None:
        """cli morph --from on a directory without keys.json exits 1 naming keys.json. Guards keys.read_chain's
        message telling the agent to run keys first."""
        code, _, err = run("morph", "--from", str(self.dir), "--out", str(self.dir / "x.mp4"), *SMALL)
        self.assertEqual(code, 1)
        self.assertIn("keys.json", err)


@requires(HAVE_FFMPEG, "needs ffmpeg and ffprobe")
class TestEffects(Base):
    def check(self, out: Path, effect: str, n_inputs: int) -> dict:
        info = probe(out)
        self.assertEqual((info["width"], info["height"]), (96, 54))
        self.assertEqual(info["r_frame_rate"], "10/1")
        self.assertEqual(info["codec_name"], "h264")
        self.assertEqual(info["pix_fmt"], "yuv420p")
        self.assertEqual(int(info["nb_read_frames"]), 10 + 5 + 5)
        strip = cv2.imread(str(out.with_name(out.stem + "_frames.png")))
        self.assertEqual(strip.shape, (720, 1920, 3))
        side = json.loads(out.with_name(out.name + ".json").read_text())
        self.assertEqual(side["effect"], effect)
        self.assertEqual(side["fps"], 10)
        self.assertEqual(side["size"], [96, 54])
        self.assertEqual(side["frames"], {"hold_start": 5, "transformation": 10, "hold_end": 5, "total": 20})
        self.assertEqual(side["duration"], 2.0)
        self.assertEqual(len(side["inputs"]), n_inputs)
        self.assertEqual(len(side["inputs"][0]["sha256"]), 64)
        for k in ("trans", "hold_start", "hold_end", "push_in"):
            self.assertIn(k, side["params"])
        self.assertTrue(side["versions"]["opencv"])
        self.assertTrue(side["versions"]["ffmpeg"])
        return side

    def test_morph(self) -> None:
        """cli morph renders an H.264 yuv420p MP4 of the computed frame count, the strip and the sidecar, with
        no warning for matching aspects. Guards the end-to-end morph output and sidecar fields."""
        out = self.dir / "m.mp4"
        code, stdout, err = run("morph", "--keys", str(self.a), str(self.mid), str(self.b), "--out", str(out), *SMALL)
        self.assertEqual(code, 0, err)
        self.assertIn(str(out), stdout)
        self.assertNotIn("warning", err)
        self.check(out, "morph", 3)

    def test_overwrite_refused(self) -> None:
        """cli crossfade refuses existing outputs without --force and replaces them with it. Guards
        frames.check_writable."""
        out = self.dir / "c.mp4"
        self.assertEqual(run("crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL)[0], 0)
        code, _, err = run("crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL)
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(run("crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL, "--force")[0], 0)

    def test_crossfade(self) -> None:
        """cli crossfade writes the MP4, strip and sidecar with effect 'crossfade' and two inputs. Guards the
        crossfade command's render path."""
        out = self.dir / "c.mp4"
        self.assertEqual(run("crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL)[0], 0)
        self.check(out, "crossfade", 2)

    def test_blur_crossfade(self) -> None:
        """cli blur-crossfade writes the clip and records --blur in the sidecar params. Guards the blur
        parameter reaching the sidecar."""
        out = self.dir / "bc.mp4"
        self.assertEqual(run("blur-crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL,
                             "--blur", "4")[0], 0)
        self.assertEqual(self.check(out, "blur-crossfade", 2)["params"]["blur"], 4)

    def test_region(self) -> None:
        """cli region with --steps 12 renders the clip and records seed and steps in the sidecar. Guards the
        region parameters in the sidecar."""
        out = self.dir / "r.mp4"
        code, _, err = run("region", "--keys", str(self.a), str(self.b), "--out", str(out), *SMALL, "--steps", "12")
        self.assertEqual(code, 0, err)
        side = self.check(out, "region", 2)
        self.assertEqual(side["params"]["seed"], 7)
        self.assertEqual(side["params"]["steps"], 12)

    def test_custom_strip_and_holds(self) -> None:
        """cli crossfade with --hold-start 0, --hold-end 1 and --strip writes the strip there and encodes 0 + 10
        + 10 frames. Guards --hold-start/--hold-end overriding --hold."""
        out, strip = self.dir / "h.mp4", self.dir / "s.png"
        code, _, err = run("crossfade", str(self.a), str(self.b), "--out", str(out), *SMALL, "--hold-start", "0",
                           "--hold-end", "1", "--strip", str(strip), "--push-in", "0")
        self.assertEqual(code, 0, err)
        self.assertTrue(strip.is_file())
        self.assertEqual(int(probe(out)["nb_read_frames"]), 0 + 10 + 10)

    def test_aspect_warning(self) -> None:
        """cli crossfade of a square image into 96x54 warns naming the file and the 2 % tolerance. Guards the
        cover-fit warning above 2 % aspect difference."""
        sq = save(self.dir / "sq.png", gradient(90, 90))
        code, _, err = run("crossfade", str(sq), str(self.b), "--out", str(self.dir / "w.mp4"), *SMALL)
        self.assertEqual(code, 0, err)
        self.assertIn("sq.png", err)
        self.assertIn("2 %", err)


@requires(HAVE_FFMPEG, "needs ffmpeg and ffprobe")
class TestChainTimes(Base):
    def test_region_default_steps(self) -> None:
        """cli region without --steps uses 2 x the transformation frames. Guards cli.default_steps."""
        out = self.dir / "r.mp4"
        code, _, err = run("region", "--keys", str(self.a), str(self.b), "--out", str(out), *SMALL)
        self.assertEqual(code, 0, err)
        side = json.loads(out.with_name(out.name + ".json").read_text())
        self.assertEqual(side["params"]["steps"], 20)  # 2 x 10 transformation frames

    def test_from_uses_fractions(self) -> None:
        """cli morph --from records the keys.json fractions as key times and --keys records equal spacing.
        Guards cli.chain choosing chain times by input mode."""
        kd = self.dir / "keys"
        keys.write(keys.plan(self.a, "pencil sketch", kd, end=self.b, fractions=[0.2]), kd, force=False)
        save(kd / "k20.png", with_disc(texture(160, 90), 54, 45, 6))
        out = self.dir / "f.mp4"
        code, _, err = run("morph", "--from", str(kd), "--out", str(out), *SMALL)
        self.assertEqual(code, 0, err)
        side = json.loads(out.with_name(out.name + ".json").read_text())
        self.assertEqual(side["params"]["key_times"], [0.0, 0.2, 1.0])
        out2 = self.dir / "k.mp4"
        code, _, err = run("morph", "--keys", str(self.a), str(kd / "k20.png"), str(self.b), "--out", str(out2), *SMALL)
        self.assertEqual(code, 0, err)
        side = json.loads(out2.with_name(out2.name + ".json").read_text())
        self.assertEqual(side["params"]["key_times"], [0.0, 0.5, 1.0])
