"""Integration: real `voiceover synth` with the Kokoro model and the MMS_FA aligner of the config template.

Runs the CLI in a child process with a config holding the template's `kokoro` and `torchaudio` providers, whose
`dir` is the default one of this machine's media plugin (`voiceover/` in its data directory), so the weights earlier
runs downloaded are reused; the first run downloads them (about 1.6 GB).
"""

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import yaml
from plugin_settings import Plugin

from tests.settings_env import write_config
from tests.subproc import child_env

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "plugins/setup/skills/settings/assets/config.example.yaml"
SCRIPTS = ROOT / "plugins/media/skills/voiceover/scripts"
SCRIPT = ("The heart pumps blood through the body.\n\nCount to five.\nIn 1995, about 42% of pumps failed.\n"
          "[calm] Keep it quiet.\n")


def template_config(path: Path) -> Path:
    """A config with the template's `kokoro` and `torchaudio` providers, `dir` the media plugin's default weights
    directory, and its `speech` and `align` models."""
    t = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    weights = str(Plugin.of(SCRIPTS).data_dir() / "voiceover")
    return write_config(path, providers={k: {**t["providers"][k], "dir": weights} for k in ("kokoro", "torchaudio")},
                        tasks={k: t["tasks"][k] for k in ("speech", "align")})


def synth(script: Path, out: Path, config: Path, *args: str) -> subprocess.CompletedProcess:
    env = child_env(SKILLS_CONFIG=str(config), HOME=str(Path.home()))
    env["PYTHONPATH"] = f"{SCRIPTS}:{env['PYTHONPATH']}"
    return subprocess.run([sys.executable, "-m", "voiceover_tool", "synth", "--script", str(script),
                           "--out-dir", str(out), *args], capture_output=True, text=True, timeout=1200, env=env)


class TestSynth(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.config = template_config(tmp / "config.yaml")
        cls.script = tmp / "script.txt"
        cls.script.write_text(SCRIPT.replace("[calm] ", ""), encoding="utf-8")
        cls.out = tmp / "out"
        r = synth(cls.script, cls.out, cls.config)
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
        model of tasks.speech and its default voice af_heart.
        Guards the default model and voice and the duration bookkeeping on real audio."""
        with wave.open(str(self.out / "narration.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 24000))
            duration = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(duration, self.timing["duration"], places=3)
        self.assertEqual((self.timing["model"], self.timing["voice"]), ("kokoro:kokoro-v1.0", "af_heart"))

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

    def test_known_word_in_second_half(self) -> None:
        """voiceover synth places the long last word of "Count to five." in the second half of the sentence.
        Guards that the aligner returns real times, not evenly spread ones."""
        s = self.timing["sentences"][1]
        self.assertEqual(s["text"], "Count to five.")
        five = s["words"][2]
        self.assertEqual(five["text"], "five.")
        # The word's midpoint, not its start: "five" begins just before the
        # sentence midpoint because "Count to" is short and "five" is long.
        self.assertGreater((five["start"] + five["end"]) / 2, (s["start"] + s["end"]) / 2)
        self.assertGreater(five["start"], s["words"][1]["end"] - 1e-9)

    def test_tag_line_refused_for_kokoro(self) -> None:
        """A `[style]` line with the Kokoro model, which takes no style or tags, is refused before any synthesis and
        writes nothing: Kokoro would speak the tag word. Guards a script written for Fish voiced by Kokoro."""
        script = self.script.with_name("styled.txt")
        script.write_text(SCRIPT, encoding="utf-8")
        out = self.out.with_name("styled")
        r = synth(script, out, self.config, "--no-align")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("would speak aloud", r.stderr)
        self.assertFalse(out.exists())

if __name__ == "__main__":
    unittest.main()
