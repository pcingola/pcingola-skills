"""keys: keys.json content, aspect choice, prompts from the assets file, --from."""

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from video_effects_tool import keys
from video_effects_tool.cli import main
from video_effects_tool.frames import EffectError

from .images import gradient, save

STYLE = "watercolour painting with soft washes"


class TestAspect(unittest.TestCase):
    def test_nearest(self) -> None:
        """keys.nearest_aspect picks the image-gen aspect closest on a log scale for landscape, portrait, square
        and wide images. Guards the aspect passed to every keyframe generation."""
        self.assertEqual(keys.nearest_aspect(2720, 1536), "16:9")
        self.assertEqual(keys.nearest_aspect(1920, 1080), "16:9")
        self.assertEqual(keys.nearest_aspect(1080, 1920), "9:16")
        self.assertEqual(keys.nearest_aspect(1000, 1000), "1:1")
        self.assertEqual(keys.nearest_aspect(3000, 2000), "3:2")
        self.assertEqual(keys.nearest_aspect(2560, 1080), "21:9")
        self.assertEqual(keys.nearest_aspect(800, 1000), "4:5")

    def test_fractions(self) -> None:
        """keys.parse_fractions accepts increasing fractions in (0, 1) and refuses empty, out-of-range,
        repeated, unsorted, non-numeric values and two fractions with the same percentage name. Same-name
        fractions would write two keyframes to one file."""
        self.assertEqual(keys.parse_fractions("0.25,0.75"), [0.25, 0.75])
        self.assertEqual(keys.parse_fractions("0.125,0.5"), [0.125, 0.5])
        for bad in ("", "0", "1", "0.5,0.5", "x", "1.2", "0.75,0.25", "0.5,0.50001", "-0.1"):
            with self.assertRaises(EffectError, msg=bad):
                keys.parse_fractions(bad)


class TestPlan(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.start = save(self.dir / "start.png", gradient(160, 90))
        self.prompts = tomllib.loads(keys.PROMPTS.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_without_end(self) -> None:
        """keys.plan without --end lists the end image first with the start as reference, then k25/k50/k75 with
        start and end as references, prompts from prompts.toml with the stage text per fraction, and the chain
        order. Guards the keys.json layout the agent follows with media:image-gen."""
        out = self.dir / "keys"
        data = keys.plan(self.start, STYLE, out)
        names = [e["name"] for e in data["images"]]
        self.assertEqual(names, ["end", "k25", "k50", "k75"])
        end = data["images"][0]
        self.assertEqual(end["refs"], [str(self.start.resolve())])
        self.assertEqual(end["out"], str(out.resolve() / "end.png"))
        self.assertEqual(end["prompt"], self.prompts["end"].format(style=STYLE))
        for e in data["images"][1:]:
            self.assertEqual(e["refs"], [str(self.start.resolve()), end["out"]])
            self.assertEqual(Path(e["out"]).parent, out.resolve())
            self.assertIn(STYLE, e["prompt"])
            self.assertEqual((e["tier"], e["model"], e["aspect"], e["size"]), ("best", None, "16:9", "2K"))
        self.assertIn("25% of the way", data["images"][1]["prompt"])
        self.assertIn(self.prompts["stage"][0]["text"], data["images"][1]["prompt"])
        self.assertIn(self.prompts["stage"][1]["text"], data["images"][2]["prompt"])
        self.assertIn(self.prompts["stage"][2]["text"], data["images"][3]["prompt"])
        self.assertEqual(data["chain"], [str(self.start.resolve()), *(e["out"] for e in data["images"][1:]),
                                         end["out"]])
        self.assertEqual(data["start"], str(self.start.resolve()))
        self.assertEqual(data["end"], end["out"])

    def test_with_end(self) -> None:
        """keys.plan with --end and one fraction lists only the in-between, referencing the given end, with the
        chosen model. Guards not regenerating a given end image."""
        end = save(self.dir / "end_given.png", gradient(160, 90, flip=True))
        data = keys.plan(self.start, STYLE, self.dir / "k", end=end, model="google/gemini-3-pro-image",
                         fractions=[0.5])
        self.assertEqual([e["name"] for e in data["images"]], ["k50"])
        self.assertEqual(data["images"][0]["refs"], [str(self.start.resolve()), str(end.resolve())])
        self.assertEqual(data["images"][0]["model"], "google/gemini-3-pro-image")
        self.assertEqual(data["end"], str(end.resolve()))

    def test_vertical_start(self) -> None:
        """keys.plan on a portrait start image sets aspect 9:16 on every image. Guards the aspect taken from the
        start image."""
        start = save(self.dir / "v.png", gradient(90, 160))
        data = keys.plan(start, STYLE, self.dir / "v")
        self.assertEqual({e["aspect"] for e in data["images"]}, {"9:16"})

    def test_refusals(self) -> None:
        """keys.plan refuses a missing or unreadable start image and an empty style. Guards checks before
        keys.json is written."""
        with self.assertRaises(EffectError):
            keys.plan(self.dir / "missing.png", STYLE, self.dir / "k")
        bad = self.dir / "bad.png"
        bad.write_text("not an image")
        with self.assertRaises(EffectError):
            keys.plan(bad, STYLE, self.dir / "k")
        with self.assertRaises(EffectError):
            keys.plan(self.start, "  ", self.dir / "k")

    def test_cli_writes_and_refuses_overwrite(self) -> None:
        """cli keys writes keys.json, refuses to replace it without --force and replaces it with --force. Guards
        keys.write."""
        out = self.dir / "kk"
        main(["keys", str(self.start), "--style", STYLE, "--dir", str(out)])
        data = json.loads((out / "keys.json").read_text())
        self.assertEqual(len(data["images"]), 4)
        with self.assertRaises(SystemExit) as cm:
            main(["keys", str(self.start), "--style", STYLE, "--dir", str(out)])
        self.assertEqual(cm.exception.code, 1)
        main(["keys", str(self.start), "--style", STYLE, "--dir", str(out), "--force", "--fractions", "0.5"])
        self.assertEqual(len(json.loads((out / "keys.json").read_text())["images"]), 2)

    def test_read_chain(self) -> None:
        """keys.read_chain names missing keyframes, then returns start, in-betweens by fraction and end with
        times 0, fractions, 1, and refuses a directory without keys.json. Guards morph --from and region --from."""
        out = self.dir / "rc"
        keys.write(keys.plan(self.start, STYLE, out, fractions=[0.2, 0.75]), out, force=False)
        with self.assertRaises(EffectError) as cm:
            keys.read_chain(out)
        self.assertIn("end.png", str(cm.exception))
        for name in ("end", "k20", "k75"):
            save(out / f"{name}.png", gradient(160, 90))
        chain, times = keys.read_chain(out)
        self.assertEqual([p.name for p in chain], ["start.png", "k20.png", "k75.png", "end.png"])
        self.assertEqual(times, [0.0, 0.2, 0.75, 1.0])
        with self.assertRaises(EffectError):
            keys.read_chain(self.dir / "nowhere")
