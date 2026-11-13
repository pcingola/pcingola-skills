"""`music generate` with the `music` model of the user's `ai_models` config (a real model call)."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from music_tool import cli


def probe(path: Path) -> tuple[float, str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    s = next(s for s in info["streams"] if s["codec_type"] == "audio")
    return float(info["format"]["duration"]), s["codec_name"]


class TestGenerate(unittest.TestCase):
    def test_instrumental_with_tempo(self) -> None:
        """`music generate --instrumental --bpm 90 --seconds 30` writes an audio file of the format the model
        returns, with a sidecar recording the model, the prompt sent and the options."""
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    cli.main(["generate", "calm piano", "--instrumental", "--bpm", "90", "--seconds", "30",
                              "-o", str(Path(tmp) / "a.mp3")])
                except SystemExit as e:
                    self.assertEqual(e.code, 0, err.getvalue())
            path = Path(out.getvalue().strip())
            dur, codec = probe(path)
            self.assertIn(codec, ("mp3", "pcm_s16le"))
            self.assertGreater(dur, 5)
            meta = json.loads(cli.sidecar(path, ".json").read_text(encoding="utf-8"))
            self.assertIn(":", meta["model"])
            self.assertEqual(meta["options"], {"instrumental": True, "bpm": 90, "seconds": 30})
            self.assertIn("90", meta["prompt"])


if __name__ == "__main__":
    unittest.main()
