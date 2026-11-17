"""Integration: kokoro-onnx phonemizes with the espeak-ng data path `ai_models.espeak` picks.

Needs no model weights. Each case runs in a fresh interpreter because
espeak-ng keeps its data path for the life of the process.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PHONEMIZE = """
import sys
from kokoro_onnx import EspeakConfig
from kokoro_onnx.tokenizer import Tokenizer
print(Tokenizer(EspeakConfig(data_path=sys.argv[1])).phonemize("The heart pumps blood.", "en-us"))
"""


def phonemize(data_path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", PHONEMIZE, data_path], capture_output=True, text=True, timeout=25
    )


class TestEspeak(unittest.TestCase):
    def test_backend_data_path(self):
        """espeak.data_path returns a path shorter than PATH_LIMIT with which kokoro-onnx phonemizes.
        Guards the espeak-ng 160-byte path limit stated in docs/ai_models.md."""
        from ai_models import espeak

        path = espeak.data_path(Path(tempfile.gettempdir()))
        self.assertLess(len(path), espeak.PATH_LIMIT)
        r = phonemize(path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip(), r.stderr)

    def test_short_copy_works(self):
        """espeak.ensure_copy of the bundled data gives a directory with which kokoro-onnx phonemizes.
        Guards that the copy, with its .source marker, is complete enough for espeak-ng."""
        import espeakng_loader

        from ai_models import espeak

        with tempfile.TemporaryDirectory() as tmp:
            dest = espeak.ensure_copy(Path(espeakng_loader.get_data_path()), Path(tmp) / "espeak-ng-data")
            self.assertLess(len(str(dest)), espeak.PATH_LIMIT)
            r = phonemize(str(dest))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.strip(), r.stderr)


if __name__ == "__main__":
    unittest.main()
