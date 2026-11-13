"""Integration: real `voiceover synth` with Kokoro and the MMS_FA aligner.

Runs the shell wrapper as a subprocess; synth downloads missing weights.
"""

import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[3] / "plugins" / "media" / "skills" / "voiceover" / "scripts" / "voiceover.sh"
SCRIPT = "The heart pumps blood through the body.\n\nCount to five.\nIn 1995, about 42% of pumps failed.\n"


class TestSynth(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        script = tmp / "script.txt"
        script.write_text(SCRIPT, encoding="utf-8")
        cls.out = tmp / "out"
        r = subprocess.run(
            [str(WRAPPER), "synth", "--script", str(script), "--out-dir", str(cls.out)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            raise AssertionError(f"synth failed ({r.returncode}):\n{r.stderr}")
        cls.stdout = r.stdout
        cls.timing = json.loads((cls.out / "timing.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_prints_both_paths(self) -> None:
        """voiceover.sh synth prints the WAV path and the timing.json path, one per line.
        Guards that stdout holds the two paths and nothing else (cli._cmd_synth)."""
        self.assertEqual(
            self.stdout.split(),
            [str(self.out / "narration.wav"), str(self.out / "timing.json")],
        )

    def test_wav_duration_matches_timing(self) -> None:
        """voiceover.sh synth with Kokoro writes a 24 kHz mono WAV whose length equals timing.json's duration, with the default backend and voice af_heart.
        Guards the default backend and the duration bookkeeping on real audio."""
        with wave.open(str(self.out / "narration.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 24000))
            duration = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(duration, self.timing["duration"], places=3)
        self.assertEqual((self.timing["backend"], self.timing["voice"]), ("kokoro", "af_heart"))

    def test_words_monotonic_inside_sentences(self) -> None:
        """voiceover.sh synth aligns every sentence with MMS_FA, a blank line skipped, numbers and percent included, with word times monotonic inside each sentence.
        Guards normalize and place_words on real model output."""
        sentences = self.timing["sentences"]
        self.assertEqual(len(sentences), 3)
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

    def test_known_word_in_second_half(self) -> None:
        """voiceover.sh synth places the long last word of "Count to five." in the second half of the sentence.
        Guards that the aligner returns real times, not evenly spread ones."""
        s = self.timing["sentences"][1]
        self.assertEqual(s["text"], "Count to five.")
        five = s["words"][2]
        self.assertEqual(five["text"], "five.")
        # The word's midpoint, not its start: "five" begins just before the
        # sentence midpoint because "Count to" is short and "five" is long.
        self.assertGreater((five["start"] + five["end"]) / 2, (s["start"] + s["end"]) / 2)
        self.assertGreater(five["start"], s["words"][1]["end"] - 1e-9)


if __name__ == "__main__":
    unittest.main()
