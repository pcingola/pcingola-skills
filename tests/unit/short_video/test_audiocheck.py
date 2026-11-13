"""short_video_tool.audiocheck: bursts and clicks in a synthetic signal."""
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from short_video_tool import audiocheck

RATE = audiocheck.RATE


def _sine(seconds: float) -> np.ndarray:
    """500 Hz (whole periods per 10 ms window, so no leakage above 16.5 kHz)
    over a low noise floor that keeps the click's own high-frequency energy
    below BURST_DB; without it the click would also count as a burst."""
    t = np.arange(int(seconds * RATE)) / RATE
    noise = np.random.default_rng(0).normal(0.0, 0.0025, t.size)
    return 0.5 * np.sin(2 * np.pi * 500.0 * t) + noise


def _write(path: Path, x: np.ndarray) -> Path:
    """`x`: one channel, or one row per channel."""
    x = np.atleast_2d(x)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x.T, -1, 1) * 32767).astype("<i2").tobytes())
    return path


class TestAudioCheck(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_sine(self) -> None:
        """audiocheck.check reports nothing on a clean sine over a noise floor. Guards against false bursts and
        clicks on normal audio."""
        self.assertEqual(audiocheck.check(_write(self.dir / "sine.wav", _sine(4.0))), [])

    def test_burst_and_click(self) -> None:
        """audiocheck.check finds an 18 kHz burst at 1.00 s and a sign-flip click at 2.50 s, one line each with
        its time and size. Guards the burst threshold above the band median and the click step ratio."""
        x = _sine(4.0)
        start, n = RATE, int(0.02 * RATE)  # 18 kHz burst at 1.00 s for 20 ms
        x[start:start + n] += 0.12 * np.sin(2 * np.pi * 18000.0 * np.arange(n) / RATE)
        flip = round((1250 + 0.25) / 500.0 * RATE)  # a peak of the sine near 2.50 s
        x[flip:] = -x[flip:]
        found = audiocheck.check(_write(self.dir / "defects.wav", x))
        self.assertEqual(len(found), 2, found)
        self.assertRegex(found[0], r"^00:01\.00 burst \+\d+ dB$")
        self.assertRegex(found[1], r"^00:02\.50 click step 1\.0\d$")

    def test_click_in_one_channel(self) -> None:
        # Opposite steps in the two channels cancel in a mono downmix; each
        # channel is checked on its own, so the step is found at full size.
        """audiocheck.check finds opposite steps in two channels that cancel in a mono downmix. Guards checking
        each channel on its own."""
        left, right = _sine(4.0), _sine(4.0)
        i = 2 * RATE
        left[i:] += 0.4
        right[i:] -= 0.4
        found = audiocheck.check(_write(self.dir / "stereo.wav", np.stack([left, right])))
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r"^00:02\.00 click step 0\.4\d$")

    def test_tone_after_silence(self) -> None:
        # The silence is left out of the burst median.
        """audiocheck.check reports nothing for a tone after 3 s of digital silence. Guards the burst median
        being taken over windows with signal only."""
        x = np.concatenate([np.zeros(3 * RATE), 0.5 * np.sin(2 * np.pi * 440.0 * np.arange(RATE) / RATE)])
        self.assertEqual(audiocheck.check(_write(self.dir / "late.wav", x)), [])

    def test_stamp_rounds_up_to_minute(self) -> None:
        """audiocheck._stamp of 59.996 s is 01:00.00, not 00:60.00. Guards rounding to centiseconds before
        splitting minutes."""
        self.assertEqual(audiocheck._stamp(59.996), "01:00.00")


if __name__ == "__main__":
    unittest.main()
