"""`fit` on a generated tone with real FFmpeg; durations and codecs checked with ffprobe."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from music_tool.fit import fit


def probe(path: Path) -> tuple[float, str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True, timeout=25).stdout
    info = json.loads(out)
    return float(info["format"]["duration"]), info["streams"][0]["codec_name"]


class TestFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.tone = cls.dir / "tone.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                        "-ac", "2", "-ar", "44100", str(cls.tone)], check=True, timeout=25)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_trim_to_10s_mp3(self) -> None:
        """fit.fit trims a 30 s tone to 10 s as MP3 with real FFmpeg. Guards the trim command and the MP3 codec
        arguments."""
        out = fit(self.tone, self.dir / "t10.mp3", 10)
        dur, codec = probe(out)
        self.assertAlmostEqual(dur, 10, delta=0.1)
        self.assertEqual(codec, "mp3")

    def test_loop_to_70s_wav(self) -> None:
        """fit.fit loops a 30 s tone to 70 s as WAV with fades. Guards that -stream_loop -1 with -t yields the
        exact target length."""
        out = fit(self.tone, self.dir / "t70.wav", 70, fade_in=1, fade_out=3)
        dur, codec = probe(out)
        self.assertAlmostEqual(dur, 70, delta=0.05)
        self.assertEqual(codec, "pcm_s16le")

    def test_m4a(self) -> None:
        """fit.fit writes a 12 s AAC M4A. Guards that the aac codec arguments are accepted by FFmpeg."""
        out = fit(self.tone, self.dir / "t12.m4a", 12)
        dur, codec = probe(out)
        self.assertAlmostEqual(dur, 12, delta=0.1)
        self.assertEqual(codec, "aac")


if __name__ == "__main__":
    unittest.main()
