"""Unit tests for voiceover_tool.normalize: written word -> aligner tokens."""

import unittest

from voiceover_tool.normalize import normalize_word


class TestNormalize(unittest.TestCase):

    def test_plain_word_lowercased_punctuation_dropped(self) -> None:
        """normalize.normalize_word lowercases a word and drops edge punctuation.
        Guards the token form the MMS_FA aligner accepts (a-z and apostrophe only)."""
        self.assertEqual(normalize_word("Heart,"), ["heart"])
        self.assertEqual(normalize_word("(body)."), ["body"])

    def test_numbers(self) -> None:
        """normalize.normalize_word spells integers with num2words, thousands separators included.
        Guards the mapping of digits, which the aligner cannot align, to spoken words."""
        self.assertEqual(normalize_word("5"), ["five"])
        self.assertEqual(normalize_word("42"), ["forty", "two"])
        self.assertEqual(normalize_word("1,000"), ["one", "thousand"])
        self.assertEqual(normalize_word("105"), ["one", "hundred", "and", "five"])

    def test_years(self) -> None:
        """normalize.normalize_word reads a standalone integer 1100..2099 as a year and others, or ones with a comma, as plain numbers.
        Guards the year rule that matches how Kokoro reads such numbers."""
        self.assertEqual(normalize_word("1995,"), ["nineteen", "ninety", "five"])
        self.assertEqual(normalize_word("2024"), ["twenty", "twenty", "four"])
        # outside 1100..2099, or with a thousands separator: a plain number
        self.assertEqual(normalize_word("3000"), ["three", "thousand"])
        self.assertEqual(normalize_word("1,995"), ["one", "thousand", "nine", "hundred", "and", "ninety", "five"])

    def test_decimals(self) -> None:
        """normalize.normalize_word reads decimals digit by digit after "point", including a leading zero and a trailing full stop.
        Guards the decimal branch of _number_words."""
        self.assertEqual(normalize_word("3.5"), ["three", "point", "five"])
        self.assertEqual(normalize_word("0.05."), ["zero", "point", "zero", "five"])

    def test_percent(self) -> None:
        """normalize.normalize_word turns `%` into "percent" for integers and decimals.
        Guards the percent rule listed in docs/voiceover.md."""
        self.assertEqual(normalize_word("42%"), ["forty", "two", "percent"])
        self.assertEqual(normalize_word("2.5%"), ["two", "point", "five", "percent"])

    def test_hyphenated(self) -> None:
        """normalize.normalize_word splits hyphenated words into their parts, numbers included.
        Guards the hyphen rule listed in docs/voiceover.md."""
        self.assertEqual(normalize_word("state-of-the-art"), ["state", "of", "the", "art"])
        self.assertEqual(normalize_word("COVID-19"), ["covid", "nineteen"])

    def test_apostrophes(self) -> None:
        """normalize.normalize_word keeps inner apostrophes, folds typographic ones and strips quoting apostrophes.
        Guards the apostrophe handling of _fold and the token strip."""
        self.assertEqual(normalize_word("don't"), ["don't"])
        self.assertEqual(normalize_word("It’s"), ["it's"])
        self.assertEqual(normalize_word("'quoted'"), ["quoted"])

    def test_punctuation_only_has_no_tokens(self) -> None:
        """normalize.normalize_word returns no tokens for a word without alignable characters.
        Guards the empty-token case that align.place_words handles by giving the word zero length."""
        for w in ("-", "—", "&", "...", "'"):
            self.assertEqual(normalize_word(w), [], w)

    def test_accents_folded(self) -> None:
        """normalize.normalize_word removes diacritics. Guards the NFKD fold, without which accented letters drop out of the token."""
        self.assertEqual(normalize_word("Café"), ["cafe"])


if __name__ == "__main__":
    unittest.main()
