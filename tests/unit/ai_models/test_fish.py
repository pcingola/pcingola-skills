"""The parts of `ai_models.fish` that need no model: the text cut at style tags (`fish_span`), the spans joined into
one WAV file (`fish.joined`), the first take of each speaker (`fish_takes.Takes`) and a take saved to a folder and
loaded back (`Take.save`, `Take.load`)."""

import io
import wave

import numpy as np
import pytest
import torch

from ai_models import AIModelsError, fish
from ai_models.fish_span import Span, split_spans
from ai_models.fish_take import Take
from ai_models.fish_takes import Takes

STYLE = "[{instructions}] {text}"


def test_text_without_tags_is_one_span():
    """A text without style tags is one span, stripped, with no speaker tag."""
    assert split_spans("  Hello there, how are you?  ") == [Span("Hello there, how are you?")]


def test_text_cut_before_each_style_tag():
    """Each style tag opens a span of the words after it; the words before the first tag are a span of their own.
    Guards Drama 3's near-silence after two tags in one request."""
    text = "[whisper] I think someone is behind the door. [laughing] Oh, it is only the cat!"
    assert split_spans(text) == [Span("[whisper] I think someone is behind the door."),
                                 Span("[laughing] Oh, it is only the cat!")]
    assert split_spans("Well [laughs] maybe that's fair.") == [Span("Well"), Span("[laughs] maybe that's fair.")]


def test_wordless_pieces_join_a_neighbour():
    """A tag followed by another tag joins the next span; a tag at the end joins the last span; a text of only a
    tag is one span."""
    assert split_spans("[sad] [whisper] Go home.") == [Span("[sad] [whisper] Go home.")]
    assert split_spans("That was funny [laughs]") == [Span("That was funny [laughs]")]
    assert split_spans("[laughs]") == [Span("[laughs]")]
    assert split_spans("   ") == []


def test_speaker_tag_stays_in_force():
    """A speaker tag at the start of a span is its `speaker` and carries to the following spans until another one
    opens a span; `said` puts it before the text."""
    spans = split_spans("<|speaker:1|>[whisper] Quiet. [shouting] Now! <|speaker:0|>[calm] Fine.")
    assert spans == [Span("[whisper] Quiet.", "<|speaker:1|>"), Span("[shouting] Now!", "<|speaker:1|>"),
                     Span("[calm] Fine.", "<|speaker:0|>")]
    assert spans[0].said(None, None) == "<|speaker:1|>[whisper] Quiet."


def test_style_only_for_spans_without_their_own_tag():
    """The instructions go into a span by the `style` format unless the span has its own style tag; without
    instructions or without a format the text is unchanged."""
    plain, tagged = split_spans("Well [laughs] maybe.")
    assert plain.styled(STYLE, " calm ") == "[calm] Well"
    assert tagged.styled(STYLE, "calm") == "[laughs] maybe."
    assert plain.styled(STYLE, None) == "Well" and plain.styled(None, "calm") == "Well"
    assert Span("Hi.", "<|speaker:2|>").said(STYLE, "calm") == "<|speaker:2|>[calm] Hi."


def test_spans_joined_in_order_at_the_codec_rate():
    """`joined` writes the float parts one after the other as one 16-bit mono WAV file at the given rate."""
    parts = [np.full(441, 0.5, dtype=np.float32), np.full((1, 882), -0.25, dtype=np.float32)]
    with wave.open(io.BytesIO(fish.joined(parts, 44_100))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (44_100, 1, 2, 1323)
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert pcm[0] == 16383 and pcm[440] == 16383 and pcm[441] == -8191 and pcm[-1] == -8191


def test_first_take_per_model_and_speaker_kept():
    """`Takes.keep` keeps the first take of each (model, speaker) and returns it on later calls; `get` gives None
    before it; `clear` forgets them all."""
    takes = Takes()
    first, later = Take(b"A", "Hi.", None), Take(b"B", "Again.", None)
    assert takes.get("f:drama-3") is None
    assert takes.keep("f:drama-3", None, first) is first
    assert takes.keep("f:drama-3", None, later) is first and takes.get("f:drama-3") is first
    assert takes.get("f:drama-3", "guest") is None and takes.get("g:drama-3") is None
    takes.keep("f:drama-3", "guest", later)
    assert takes.get("f:drama-3", "guest") is later
    takes.clear()
    assert takes.get("f:drama-3") is None and takes.get("f:drama-3", "guest") is None


def test_take_save_and_load_round_trip(tmp_path):
    """`Take.save` writes `voice.wav`, `voice.txt` and `codes.pt` to a folder it creates, and `Take.load` reads the
    same WAV bytes, styled text and codes tensor back; a folder without one of the files is refused with its name.
    Guards the Fish voice that a later voiceover command reuses (docs/ai_models.md, Fish)."""
    codes = torch.arange(30, dtype=torch.long).reshape(10, 3)
    folder = Take(b"RIFF-wav", "[calm] Hello there.", codes).save(tmp_path / "anna.fish")
    assert sorted(p.name for p in folder.iterdir()) == ["codes.pt", "voice.txt", "voice.wav"]
    back = Take.load(folder)
    assert (back.wav, back.text) == (b"RIFF-wav", "[calm] Hello there.")
    assert back.codes.dtype == torch.long and torch.equal(back.codes, codes)
    (folder / "codes.pt").unlink()
    with pytest.raises(AIModelsError, match="codes.pt"):
        Take.load(folder)
