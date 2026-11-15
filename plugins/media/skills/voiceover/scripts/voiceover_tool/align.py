"""Word timing: forced alignment of each sentence clip against its known text.

`sentence_words` is the model-free core: it normalises the words, asks an
`align_fn` for the time span of every aligner token, and places each written
word. If `align_fn` raises, the words are spread over the sentence in
proportion to their character length and the sentence is marked unaligned.
`clip_aligner` gives the real `align_fn`: the align model of the `ai_models` config (a torchaudio forced-alignment
pipeline, CPU).
"""

from __future__ import annotations

import sys
from typing import Callable, Sequence

import numpy as np

from .normalize import normalize_word

# (tokens) -> one (start, end) per token, in seconds from the start of the clip
AlignFn = Callable[[Sequence[str]], Sequence[tuple[float, float]]]


def proportional_word_times(words: Sequence[str], start: float, end: float) -> list[tuple[float, float]]:
    """Spread words over [start, end] in proportion to their character length."""
    if not words:
        return []
    lengths = [max(1, len(w)) for w in words]
    total = float(sum(lengths))
    span = max(0.0, end - start)
    out: list[tuple[float, float]] = []
    acc = 0
    for n in lengths:
        s = start + span * acc / total
        acc += n
        out.append((s, start + span * acc / total))
    return out


def place_words(
    word_tokens: Sequence[Sequence[str]],
    token_spans: Sequence[tuple[float, float]],
    start: float,
    end: float,
) -> list[tuple[float, float]]:
    """Turn per-token spans (clip-relative) into per-word times (absolute).

    A word spanning several tokens takes the first token's start and the last
    token's end. A word with no tokens gets start = end = the previous word's
    end, or the sentence start for the first word. Times are clamped to
    [start, end] and kept monotonic.
    """
    n_tokens = sum(len(t) for t in word_tokens)
    if len(token_spans) != n_tokens:
        raise ValueError(f"{len(token_spans)} token spans for {n_tokens} tokens")
    out: list[tuple[float, float]] = []
    prev_end = start
    i = 0
    for toks in word_tokens:
        if not toks:
            out.append((prev_end, prev_end))
            continue
        s = start + token_spans[i][0]
        e = start + token_spans[i + len(toks) - 1][1]
        i += len(toks)
        s = min(max(s, prev_end), end)
        e = min(max(e, s), end)
        out.append((s, e))
        prev_end = e
    return out


def sentence_words(
    text: str,
    start: float,
    end: float,
    align_fn: AlignFn,
    index: int | None = None,
) -> tuple[list[tuple[str, float, float]], bool]:
    """Return ([(word as written, start, end)], aligned) for one sentence."""
    words = text.split()
    word_tokens = [normalize_word(w) for w in words]
    flat = [t for toks in word_tokens for t in toks]
    try:
        spans = list(align_fn(flat)) if flat else []
        times = place_words(word_tokens, spans, start, end)
        aligned = True
    except Exception as e:  # noqa: BLE001 - a wrong word time beats a failed run
        label = f"sentence {index}" if index is not None else "sentence"
        print(f"Warning: alignment failed for {label} ({e}); using proportional word times", file=sys.stderr)
        times = proportional_word_times(words, start, end)
        aligned = False
    return [(w, s, e) for w, (s, e) in zip(words, times)], aligned


def clip_aligner(model: str | None = None) -> Callable[[np.ndarray, int], AlignFn]:
    """The `align_fn` maker of align model `model` (else `models.align` of the `ai_models` config): for a clip and
    its sample rate, the function that aligns tokens against that clip. Loads the model; `AIModelsError` when it
    cannot."""
    from ai_models import align

    aligner = align.aligner(model)
    return lambda clip, sr: (lambda tokens: aligner.align(clip, sr, tokens))
