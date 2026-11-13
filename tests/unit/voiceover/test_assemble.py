"""Unit tests for voiceover_tool.assemble: join offsets and silence trimming."""

import unittest

import numpy as np

from voiceover_tool.assemble import join, trim_silence

SR = 1000


class TestJoin(unittest.TestCase):

    def test_offsets_with_lead_gap_tail(self) -> None:
        """assemble.join returns each clip's span after the lead and gaps, and the total length with the tail.
        Guards the exact sentence times timing.json records, which come only from these offsets."""
        clips = [np.ones(500, np.float32), np.ones(1200, np.float32), np.ones(300, np.float32)]
        audio, spans = join(clips, SR, lead=0.25, gap=0.35, tail=0.6)
        self.assertEqual(spans, [(0.25, 0.75), (1.1, 2.3), (2.65, 2.95)])
        self.assertEqual(audio.size, 250 + 500 + 350 + 1200 + 350 + 300 + 600)

    def test_silence_where_expected(self) -> None:
        """assemble.join places each clip's samples inside its returned span and silence elsewhere.
        Guards that the spans describe the audio actually written, not only its length."""
        clips = [np.full(100, 0.5, np.float32), np.full(100, 0.5, np.float32)]
        audio, spans = join(clips, SR, lead=0.1, gap=0.2, tail=0.3)
        for start, end in spans:
            self.assertTrue(np.all(audio[round(start * SR):round(end * SR)] == 0.5))
        self.assertTrue(np.all(audio[:100] == 0))
        self.assertTrue(np.all(audio[200:400] == 0))
        self.assertTrue(np.all(audio[500:] == 0))
        self.assertEqual(audio.size, 800)

    def test_single_clip_no_gap(self) -> None:
        """assemble.join with one clip inserts no gap. Guards the rule that gaps go only between clips."""
        audio, spans = join([np.ones(400, np.float32)], SR, lead=0.0, gap=5.0, tail=0.0)
        self.assertEqual(spans, [(0.0, 0.4)])
        self.assertEqual(audio.size, 400)


class TestTrimSilence(unittest.TestCase):

    def test_trims_leading_and_trailing_keeping_30ms(self) -> None:
        """assemble.trim_silence removes quiet audio at both ends and keeps 30 ms around the loud part.
        Guards the padding that keeps word onsets from being cut."""
        sr = 24000
        tone = np.full(sr, 0.5, np.float32)
        quiet = np.full(sr // 2, 1e-4, np.float32)  # -80 dBFS
        clip = np.concatenate([quiet, tone, quiet])
        out = trim_silence(clip, sr)
        keep = round(0.030 * sr)
        self.assertEqual(out.size, tone.size + 2 * keep)
        self.assertTrue(np.all(np.abs(out[:keep]) < 1e-3))

    def test_no_silence_unchanged(self) -> None:
        """assemble.trim_silence leaves a clip loud from start to end unchanged. Guards the clamp of the padding to the clip bounds."""
        clip = np.full(1000, 0.2, np.float32)
        self.assertEqual(trim_silence(clip, SR).size, 1000)

    def test_all_silent_returns_empty(self) -> None:
        """assemble.trim_silence returns an empty array for a clip entirely below the threshold.
        Guards the explicit all-silent branch."""
        self.assertEqual(trim_silence(np.full(5000, 1e-4, np.float32), SR).size, 0)
        self.assertEqual(trim_silence(np.zeros(5000, np.float32), SR).size, 0)

    def test_threshold_is_minus_50_dbfs(self) -> None:
        """assemble.trim_silence keeps a sample at -49 dBFS and drops one at -51 dBFS.
        Guards the -50 dBFS threshold stated in docs/voiceover.md."""
        clip = np.zeros(3000, np.float32)
        clip[1500] = 10 ** (-49 / 20)  # just above -50 dBFS
        clip[100] = 10 ** (-51 / 20)  # just below
        out = trim_silence(clip, SR)
        self.assertEqual(out.size, 2 * 30 + 1)


if __name__ == "__main__":
    unittest.main()
