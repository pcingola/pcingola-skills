"""Map a word as written to the tokens the MMS_FA aligner sees (English only).

Lowercase; keep `a-z` and `'`; digits become words with num2words (an integer
from 1100 to 2099 standing alone is read as a year, as Kokoro reads it);
decimals are read digit by digit after "point"; `%` becomes "percent";
hyphenated words split into parts. A word with no alignable characters (a dash,
`&` alone) maps to no tokens.
"""

from __future__ import annotations

import re
import unicodedata

from num2words import num2words

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_SPLIT = re.compile(r"[^a-z']+")
_EDGE_PUNCT = re.compile(r"^[^\w]+|[^\w%]+$")
_DIGIT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def _fold(word: str) -> str:
    w = unicodedata.normalize("NFKD", word)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return w.replace("’", "'").replace("‘", "'").lower()


def _number_words(text: str, standalone: bool) -> str:
    if "." in text:
        whole, _, frac = text.replace(",", "").partition(".")
        head = num2words(int(whole)) if whole else "zero"
        return f" {head} point {' '.join(_DIGIT_WORDS[int(d)] for d in frac)} "
    value = int(text.replace(",", ""))
    if standalone and "," not in text and 1100 <= value <= 2099:
        return f" {num2words(value, to='year')} "
    return f" {num2words(value)} "


def normalize_word(word: str) -> list[str]:
    """Return the aligner tokens for one written word (possibly none)."""
    w = _fold(word)
    core = _EDGE_PUNCT.sub("", w)
    standalone = bool(core) and core.isdigit()
    w = w.replace("%", " percent ")
    w = _NUMBER.sub(lambda m: _number_words(m.group(), standalone), w)
    tokens = (t.strip("'") for t in _SPLIT.split(w))
    return [t for t in tokens if t]
