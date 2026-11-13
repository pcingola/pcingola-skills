"""Unit tests for word placement, without any model. The synth pipeline with the
real Kokoro backend and aligner is in tests/integration/voiceover/test_synth.py."""

import unittest

from voiceover_tool.align import place_words, proportional_word_times


def assert_monotonic_inside(tc: unittest.TestCase, times, start: float, end: float) -> None:
    prev = start
    for s, e in times:
        tc.assertGreaterEqual(s, prev - 1e-9)
        tc.assertGreaterEqual(e, s)
        tc.assertLessEqual(e, end + 1e-9)
        prev = e


class TestWordPlacement(unittest.TestCase):

    def test_proportional_fallback(self) -> None:
        """align.proportional_word_times spreads words over the sentence in proportion to their character length.
        Guards the fallback word times used when alignment fails."""
        words = ["The", "heart", "pumps", "blood."]
        times = proportional_word_times(words, 2.0, 4.0)
        assert_monotonic_inside(self, times, 2.0, 4.0)
        self.assertAlmostEqual(times[0][0], 2.0)
        self.assertAlmostEqual(times[-1][1], 4.0)
        # "heart" (5 of 19 chars) gets 5/19 of the span
        self.assertAlmostEqual(times[1][1] - times[1][0], 2.0 * 5 / 19)

    def test_no_token_words(self) -> None:
        """align.place_words gives a word with no tokens zero length at the previous word's end (the sentence start for the first) and a multi-token word its first start and last end.
        Guards the rules stated in place_words for dashes and numbers."""
        word_tokens = [[], ["a"], [], ["b", "c"], []]
        spans = [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)]
        times = place_words(word_tokens, spans, 1.0, 2.0)
        self.assertEqual(times[0], (1.0, 1.0))  # first word: sentence start
        self.assertAlmostEqual(times[1][0], 1.1)
        self.assertAlmostEqual(times[2][0], times[1][1])  # previous word's end
        self.assertEqual(times[2][0], times[2][1])
        self.assertAlmostEqual(times[3][0], 1.3)  # first token's start
        self.assertAlmostEqual(times[3][1], 1.6)  # last token's end
        self.assertEqual(times[4], (times[3][1], times[3][1]))
        assert_monotonic_inside(self, times, 1.0, 2.0)

    def test_spans_clamped_to_sentence(self) -> None:
        """align.place_words clamps overlapping or overlong token spans into the sentence and keeps times monotonic.
        Guards against word times outside their sentence."""
        times = place_words([["a"], ["b"]], [(0.0, 0.9), (0.8, 1.5)], 1.0, 2.0)
        assert_monotonic_inside(self, times, 1.0, 2.0)
        self.assertEqual(times[1][1], 2.0)


if __name__ == "__main__":
    unittest.main()
