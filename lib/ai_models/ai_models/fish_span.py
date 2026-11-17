"""A Fish text cut into spans at its style tags (`split_spans`), one fish-speech request per span.

Fish Audio Drama 3 ends a request with one style tag (`[whisper] ...`) on its own; with two tags in one request
the speech is right and near-silence follows it up to the token cap. So the text is cut before each style tag: each
span holds the words that follow one tag. A piece with no words (a tag before another tag) joins the next piece, or
at the end of the text the previous span. A speaker tag (`<|speaker:N|>`) at the start of a span is that span's
`speaker`, and it stays in force for the following spans of the text until another one starts a span. A span
without a speaker tag is speaker 0 to the model (fish-speech's `with_speaker_tag` adds `<|speaker:0|>`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STYLE_TAG_RE = re.compile(r"\[[^\[\]]*\]")
SPEAKER_TAG_RE = re.compile(r"\s*(<\|speaker:(\d+)\|>)\s*")
ANY_TAG_RE = re.compile(r"\[[^\[\]]*\]|<\|[^|]*\|>")
CUT_RE = re.compile(r"(?:<\|speaker:\d+\|>\s*)?\[[^\[\]]*\]")  # a style tag with the speaker tag right before it


def has_words(text: str) -> bool:
    """True when `text` holds something besides tags and white space."""
    return bool(ANY_TAG_RE.sub("", text).strip())


@dataclass(frozen=True)
class Span:
    """One request's text: `text` (its words, with its style tag when it has one) and `speaker`, the speaker tag in
    force (empty for none)."""

    text: str
    speaker: str = ""

    @property
    def speaker_id(self) -> int:
        """The number of the span's speaker tag; 0 without one, as the model reads an untagged text."""
        m = SPEAKER_TAG_RE.match(self.speaker)
        return int(m.group(2)) if m else 0

    def with_speaker(self, text: str) -> str:
        """`text` after the span's speaker tag: the request text, and the reference transcript, so that the
        reference voices the speaker the request names."""
        return self.speaker + text

    @property
    def tagged(self) -> bool:
        """True when the span starts with a style tag of its own."""
        return STYLE_TAG_RE.match(self.text) is not None

    def styled(self, style: str | None, instructions: str | None) -> str:
        """The span's text with `instructions` put in by the `style` format ({instructions}, {text}); unchanged when
        the span has its own style tag or there are no instructions."""
        if self.tagged or not instructions or not style:
            return self.text
        return style.format(instructions=instructions.strip(), text=self.text)

    def said(self, style: str | None, instructions: str | None) -> str:
        """What the model gets: the speaker tag, then `styled`."""
        return self.with_speaker(self.styled(style, instructions))


def pieces(text: str) -> list[str]:
    """`text` cut before each style tag (and a speaker tag right before it) that does not open it, each piece with
    words; a wordless piece joins the next one, or the last piece at the end."""
    cuts = [0, *(m.start() for m in CUT_RE.finditer(text) if m.start() > 0), len(text)]
    out: list[str] = []
    pending = ""
    for start, end in zip(cuts, cuts[1:]):
        piece = pending + text[start:end]
        if has_words(piece):
            out.append(piece)
            pending = ""
        else:
            pending = piece
    if pending and out:
        out[-1] += pending
    elif pending:
        out.append(pending)
    return out


def split_spans(text: str) -> list[Span]:
    """The spans of `text` (module docstring), white space stripped; empty for a text without anything in it."""
    spans: list[Span] = []
    speaker = ""
    for piece in pieces(text):
        if m := SPEAKER_TAG_RE.match(piece):
            speaker, piece = m.group(1), piece[m.end():]
        if piece := piece.strip():
            spans.append(Span(piece, speaker))
    return spans
