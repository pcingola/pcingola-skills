"""`music analyze` through the CLI on synthetic clips made with FFmpeg.

Signal and images run offline; the model analysis uses the `audio` model of
tests/config.yaml.
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from music_tool import cli
from plugin_settings import use

from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG

SCRIPTS = Path(__file__).resolve().parents[3] / "plugins/media/skills/music/scripts"

DRUMS = "0.8*sin(2*PI*60*t)*exp(-30*mod(t,0.5))+0.3*(random(0)*2-1)*exp(-80*mod(t,0.5))"  # 120 BPM
PAD = "(0.2*sin(2*PI*220*t)+0.15*sin(2*PI*277.18*t)+0.15*sin(2*PI*329.63*t))*(0.8+0.2*sin(2*PI*0.1*t))"  # A major


def make(path: Path, expr: str, seconds: int = 20) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={seconds}",
                    "-ac", "2", str(path)], check=True, timeout=25)


def analyze(argv: list[str]) -> int:
    """The exit code of `music analyze <argv>` run in process with tests/config.yaml."""
    use(TEST_CONFIG)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["analyze", *argv])
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        use(None)
    return 0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestAnalyze(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name) / "clips"
        cls.dir.mkdir()
        make(cls.dir / "drums.wav", DRUMS)
        make(cls.dir / "pad.mp3", PAD)
        (cls.dir / "prompts.txt").write_text("drums.wav: driving kick, 120 BPM\npad.mp3: calm pad, 90 BPM\n")
        cls.before = {p.name: digest(p) for p in cls.dir.iterdir()}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def report(self, out: Path, name: str) -> dict:
        return json.loads((out / f"{name}.json").read_text(encoding="utf-8"))

    def test_signal_and_images(self) -> None:
        """`music analyze --only signal --only images` on an FFmpeg drum loop and A-major pad writes reports with
        the prompts-file tempo, a matching tempo, percussive ratios, key, loudness, PNGs and a summary, and
        leaves the inputs unchanged. Guards the offline analyze pipeline end to end and the rule that inputs
        are only read."""
        code = analyze([str(self.dir), "--prompts", str(self.dir / "prompts.txt"), "--only", "signal",
                        "--only", "images"])
        self.assertEqual(code, 0)
        out = self.dir / "analysis"
        drums, pad = self.report(out, "drums"), self.report(out, "pad")
        self.assertNotIn("model", drums)
        self.assertEqual(drums["brief"]["requested_bpm"], 120.0)
        self.assertEqual(drums["checks"]["tempo"]["relation"], "match")
        self.assertLess(drums["signal"]["ibi_cv"], 0.05)
        self.assertGreater(drums["signal"]["percussive_ratio"], 0.8)
        self.assertLess(pad["signal"]["percussive_ratio"], 0.05)
        self.assertIsNone(pad["signal"]["tempo_bpm"])
        self.assertEqual((pad["signal"]["key"], pad["signal"]["mode"]), ("A", "major"))
        self.assertIsNotNone(pad["signal"]["integrated_lufs"])
        for name in ("drums", "pad"):
            for suffix in ("_spec.png", "_wave.png"):
                self.assertEqual((out / f"{name}{suffix}").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        summary = (out / "summary.md").read_text()
        self.assertIn("## drums", summary)
        self.assertIn("Verdict: no model verdict (model analysis not run).", summary)
        self.assertEqual({p.name: digest(p) for p in self.dir.iterdir() if p.is_file()}, self.before)

    def test_model_section_without_audio_model(self) -> None:
        """`music analyze --only model` with a config that names no `audio` model exits 0 with the model section
        `skipped` and the reason in summary.md."""
        out = Path(self._tmp.name) / "skip"
        config = Path(self._tmp.name) / "config.yaml"
        config.write_text("providers: {}\ntasks: {}\n")
        env = {**os.environ, "SKILLS_CONFIG": str(config),
               "PYTHONPATH": os.pathsep.join([str(SCRIPTS), os.environ.get("PYTHONPATH", "")])}
        p = subprocess.run([sys.executable, "-m", "music_tool", "analyze", str(self.dir / "pad.mp3"), "--only",
                            "model", "--out-dir", str(out)], env=env, capture_output=True, text=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.report(out, "pad")["model"]["status"], "skipped")
        self.assertIn("no model for task 'audio'", (out / "summary.md").read_text())

    def test_model(self) -> None:
        """`music analyze --only model` with the `audio` model of tests/config.yaml returns a description, a
        style-brief verdict and `no brief` for the missing clip brief. Guards the describe requests against a real
        audio model and their schema handling."""
        require_ollama("audio")
        out = Path(self._tmp.name) / "model"
        code = analyze([str(self.dir / "drums.wav"), "--only", "model", "--brief", "instrumental drum loop",
                        "--out-dir", str(out)])
        self.assertEqual(code, 0)
        m = self.report(out, "drums")["model"]
        self.assertEqual(m["status"], "ok", m)
        self.assertIn(m["style_brief_verdict"], ["fits", "partly", "does not fit"])
        self.assertEqual(m["clip_brief_verdict"], "no brief")
        self.assertIsInstance(m["instruments"], list)


if __name__ == "__main__":
    unittest.main()
