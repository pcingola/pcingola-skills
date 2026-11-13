"""Unit tests for music_tool.measure on synthetic signals and fixed inputs."""

import unittest

import numpy as np

from music_tool import measure

SR = measure.SR


def click_track(bpm: float, seconds: float = 20.0) -> np.ndarray:
    """Decaying noise bursts on every beat."""
    rng = np.random.default_rng(0)
    t = np.arange(int(SR * seconds)) / SR
    phase = np.mod(t, 60.0 / bpm)
    return (0.5 * (rng.random(t.size) * 2 - 1) * np.exp(-60 * phase)).astype(np.float32)


def chord(freqs: list[float], seconds: float = 20.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (sum(0.15 * np.sin(2 * np.pi * f * t) for f in freqs)).astype(np.float32)


class TestLevelLabel(unittest.TestCase):

    def test_flat(self) -> None:
        """measure.level_label labels a steady level `flat` after dropping the fade windows. Guards that fade-in
        and fade-out windows do not create a trend."""
        self.assertEqual(measure.level_label([-30] + [-14] * 10 + [-30])[0], "flat")

    def test_building_ignores_fades(self) -> None:
        """measure.level_label labels a rising level `building` with a trend above TREND_DB, ignoring quiet first
        and last windows. Guards the building rule and the fade-window drop."""
        windows = [-40, -22, -21, -20, -16, -15, -14, -12, -11, -10, -40]
        label, trend = measure.level_label(windows)
        self.assertEqual(label, "building")
        self.assertGreater(trend, measure.TREND_DB)

    def test_decaying(self) -> None:
        """measure.level_label labels a falling level `decaying`. Guards the decaying rule."""
        self.assertEqual(measure.level_label([-10, -10, -11, -12, -15, -16, -18, -19, -20])[0], "decaying")

    def test_sparse(self) -> None:
        """measure.level_label labels a clip with many windows 20 dB below the loudest `sparse`. Guards the
        sparse rule taking precedence over the trend."""
        self.assertEqual(measure.level_label([-12, -50, -12, -55, -60, -12, -12, -58])[0], "sparse")

    def test_empty(self) -> None:
        """measure.level_label returns (`sparse`, 0.0) for no windows. Guards the empty-input case."""
        self.assertEqual(measure.level_label([]), ("sparse", 0.0))

    def test_silent(self) -> None:
        """measure.level_label returns `silent` when the loudest window is below -60 dBFS. Guards the silent
        rule."""
        self.assertEqual(measure.level_label([-200.0] * 5), ("silent", 0.0))


class TestWindowRms(unittest.TestCase):

    def test_full_scale_sine_and_partial_window(self) -> None:
        """measure.window_rms_db keeps a last partial window of at least half a window and measures a full-scale
        sine at -3 dBFS. Guards the window rule and the dBFS scale."""
        t = np.arange(int(SR * 5)) / SR
        y = np.sin(2 * np.pi * 440 * t)
        w = measure.window_rms_db(y, SR, 2.0)
        self.assertEqual(len(w), 3)  # 2 s, 2 s, then a 1 s window (half a window is kept)
        self.assertAlmostEqual(w[0], -3.0, delta=0.1)

    def test_short_tail_dropped(self) -> None:
        """measure.window_rms_db drops a last window shorter than half a window. Guards the partial-window rule."""
        self.assertEqual(len(measure.window_rms_db(np.ones(int(SR * 4.5)), SR, 2.0)), 2)

    def test_clip_shorter_than_half_a_window(self) -> None:
        """measure.window_rms_db returns one window for a clip shorter than half a window. Guards that short
        clips still get a level."""
        self.assertEqual(measure.window_rms_db(np.ones(int(SR * 0.5)), SR, 2.0), [0.0])


class TestTempoRelation(unittest.TestCase):

    def test_relations(self) -> None:
        """measure.tempo_relation returns match, half, double or differs within the tolerance and None when
        either tempo is missing. Guards the tempo comparison used by the checks."""
        self.assertEqual(measure.tempo_relation(123, 124), "match")
        self.assertEqual(measure.tempo_relation(62, 124), "half")
        self.assertEqual(measure.tempo_relation(246, 124), "double")
        self.assertEqual(measure.tempo_relation(152, 115), "differs")
        self.assertIsNone(measure.tempo_relation(120, None))
        self.assertIsNone(measure.tempo_relation(None, 120))


class TestKey(unittest.TestCase):

    def test_profiles_recovered(self) -> None:
        """measure.estimate_key recovers the tonic and mode of a rotated Krumhansl-Kessler profile. Guards the
        key estimate's rotation and mode choice."""
        self.assertEqual(measure.estimate_key(np.roll(measure.MAJOR, 9))["key"], "A")
        self.assertEqual(measure.estimate_key(np.roll(measure.MAJOR, 9))["mode"], "major")
        k = measure.estimate_key(np.roll(measure.MINOR, 4))
        self.assertEqual((k["key"], k["mode"]), ("E", "minor"))
        self.assertAlmostEqual(k["correlation"], 1.0, places=3)

    def test_flat_chroma_has_no_key(self) -> None:
        """measure.estimate_key returns no key for zero or NaN chroma. Guards the no-key rule for silence and
        flat chroma."""
        self.assertIsNone(measure.estimate_key(np.zeros(12))["key"])
        self.assertIsNone(measure.estimate_key(np.full(12, np.nan))["key"])


class TestEbur128(unittest.TestCase):

    SUMMARY = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -14.5 LUFS
    Threshold: -24.8 LUFS

  Loudness range:
    LRA:         3.2 LU
    Threshold: -34.9 LUFS
    LRA low:   -16.1 LUFS
    LRA high:  -12.9 LUFS

  True peak:
    Peak:       -1.9 dBFS
"""

    def test_parse(self) -> None:
        """measure.parse_ebur128 reads integrated loudness, loudness range and true peak from the Summary block,
        not the running lines. Guards the parser of FFmpeg's ebur128 output."""
        self.assertEqual(measure.parse_ebur128("t: 1 M: -20 S: -20 I: -30 LUFS\n" + self.SUMMARY),
                         {"integrated_lufs": -14.5, "loudness_range_lu": 3.2, "true_peak_dbtp": -1.9})

    def test_silence(self) -> None:
        """measure.parse_ebur128 returns None for `-inf` loudness and peak. Guards JSON-safe values for silent
        clips."""
        text = self.SUMMARY.replace("-14.5 LUFS", "-inf LUFS").replace("-1.9 dBFS", "-inf dBFS")
        out = measure.parse_ebur128(text)
        self.assertIsNone(out["integrated_lufs"])
        self.assertIsNone(out["true_peak_dbtp"])


class TestMeasureSamples(unittest.TestCase):

    def test_click_track(self) -> None:
        """measure.measure_samples on a 120 BPM click track gives a matching tempo, high percussive ratio,
        regular pulse, 2 onsets/s and the requested-tempo confidence. Guards the tempo, pulse and HPSS
        measurements together."""
        m = measure.measure_samples(click_track(120), requested_bpm=120)
        self.assertEqual(measure.tempo_relation(m["tempo_bpm"], 120), "match")
        self.assertGreater(m["percussive_ratio"], 0.8)
        self.assertEqual(m["pulse"], "regular")
        self.assertLess(m["ibi_cv"], 0.05)
        self.assertAlmostEqual(m["onset_rate_per_s"], 2.0, delta=0.3)
        self.assertIn("requested_bpm_confidence", m)

    def test_sustained_chord(self) -> None:
        """measure.measure_samples on an A-major chord gives no tempo, no onsets, key A major and a flat level,
        and no requested-tempo confidence. Guards the ONSET_MIN rule that keeps a steady tone from getting a
        tempo."""
        m = measure.measure_samples(chord([220.0, 277.18, 329.63]), requested_bpm=90)
        self.assertLess(m["percussive_ratio"], 0.05)
        self.assertIsNone(m["tempo_bpm"])
        self.assertEqual(m["pulse"], "none")
        self.assertEqual(m["onset_rate_per_s"], 0.0)
        self.assertEqual((m["key"], m["mode"]), ("A", "major"))
        self.assertEqual(m["level"], "flat")
        self.assertNotIn("requested_bpm_confidence", m)
        self.assertTrue(measure.summary_line(m).startswith("no tempo, pulse none"))


class TestEdgeClips(unittest.TestCase):

    def test_silence(self) -> None:
        """measure.measure_samples on silence gives a silent level, no key, no tempo and a result that serialises
        without NaN. Guards the report of a silent clip."""
        m = measure.measure_samples(np.zeros(SR * 6, dtype=np.float32), requested_bpm=100)
        self.assertEqual(m["level"], "silent")
        self.assertIsNone(m["key"])
        self.assertIsNone(m["tempo_bpm"])
        self.assertIn("no key", measure.summary_line(m))
        import json
        json.dumps(m, allow_nan=False)

    def test_short_clip(self) -> None:
        """measure.measure_samples on a 0.5 s clip gives no tempo or key and one level window. Guards the rule of
        no tempo or key under 2 s."""
        m = measure.measure_samples(click_track(120, seconds=0.5))
        self.assertIsNone(m["tempo_bpm"])
        self.assertIsNone(m["key"])
        self.assertEqual(len(m["rms_dbfs"]), 1)
        self.assertGreater(m["percussive_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
