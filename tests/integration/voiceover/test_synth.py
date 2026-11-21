"""Integration: real `voiceover synth` with the `speech` and `align` models of tests/config.yaml.

Calls the CLI's `main(argv)` in process under TEST_CONFIG (`tests.inproc.run_main`), so one call checks the printed
paths an agent reads and the files the command writes. The models are loaded once, in the class setup; the autouse
`_unload_local_models` fixture drops them after the first test.
"""

import json
import tempfile
import unittest
import wave
from pathlib import Path

from tests.inproc import CliResult, run_main
from tests.settings_env import TEST_CONFIG, model_entry, task_model
from voiceover_tool.cli import main

SCRIPT = ("The heart pumps blood through the body.\n\nCount to five.\nIn 1995, about 42% of pumps failed.\n"
          "[calm] Keep it quiet.\n")


def synth(script: Path, out: Path, *args: str) -> CliResult:
    """`voiceover synth` of `script` into `out` with `args`, in process under TEST_CONFIG."""
    return run_main(main, "synth", "--script", str(script), "--out-dir", str(out), *args, settings=TEST_CONFIG)


class TestSynth(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.script = tmp / "script.txt"
        cls.script.write_text(SCRIPT.replace("[calm] ", ""), encoding="utf-8")
        cls.out = tmp / "out"
        r = synth(cls.script, cls.out)
        if r.returncode != 0:
            raise AssertionError(f"synth failed ({r.returncode}):\n{r.stderr}")
        cls.stdout = r.stdout
        cls.timing = json.loads((cls.out / "timing.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_prints_both_paths(self) -> None:
        """voiceover synth prints the WAV path and the timing.json path, one per line.
        Guards that stdout holds the two paths and nothing else (cli._cmd_synth)."""
        self.assertEqual(self.stdout.split(), [str(self.out / "narration.wav"), str(self.out / "timing.json")])

    def test_wav_duration_matches_timing(self) -> None:
        """voiceover synth with Kokoro writes a 24 kHz mono WAV whose length equals timing.json's duration, with the
        model of tasks.speech and the default voice of its entry.
        Guards the default model and voice and the duration bookkeeping on real audio."""
        with wave.open(str(self.out / "narration.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 24000))
            duration = w.getnframes() / w.getframerate()
        # timing.json rounds the duration to 3 decimals, so they differ by at most half a millisecond
        self.assertLessEqual(abs(duration - self.timing["duration"]), 0.0005 + 1e-9)
        self.assertEqual((self.timing["model"], self.timing["voice"]), (task_model("speech"), model_entry("speech")["voice"]))

    def test_words_monotonic_inside_sentences(self) -> None:
        """voiceover synth aligns every sentence with MMS_FA, a blank line skipped, numbers and percent included,
        with word times monotonic inside each sentence.
        Guards normalize and place_words on real model output."""
        sentences = self.timing["sentences"]
        self.assertEqual(len(sentences), 4)
        prev_end = 0.0
        for s in sentences:
            self.assertTrue(s["aligned"], s["text"])
            self.assertGreater(s["start"], prev_end - 1e-9)
            self.assertEqual([w["text"] for w in s["words"]], s["text"].split())
            t = s["start"]
            for w in s["words"]:
                self.assertGreaterEqual(w["start"], t)
                self.assertGreaterEqual(w["end"], w["start"])
                self.assertLessEqual(w["end"], s["end"])
                t = w["end"]
            prev_end = s["end"]
        self.assertLessEqual(prev_end, self.timing["duration"])

    def test_tag_line_refused_for_kokoro(self) -> None:
        """A `[style]` line with the Kokoro model, which takes no style or tags, is refused before any synthesis and
        writes nothing: Kokoro would speak the tag word. Guards a script written for Fish voiced by Kokoro."""
        script = self.script.with_name("styled.txt")
        script.write_text(SCRIPT, encoding="utf-8")
        out = self.out.with_name("styled")
        r = synth(script, out, "--no-align")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("would speak aloud", r.stderr)
        self.assertFalse(out.exists())

if __name__ == "__main__":
    unittest.main()
