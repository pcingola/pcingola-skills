"""The parts of `ai_models.fish` that need no model: the text cut at style tags (`fish_span`), the spans joined into
one WAV file (`fish.joined`), the first take of each voice (`fish_takes.Takes`) and a take saved to a folder and
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


def test_span_speaker_id_and_reference_transcript():
    """`speaker_id` is the number of a span's speaker tag and 0 without one, as fish-speech reads an untagged
    text; `with_speaker` puts the span's tag before a reference transcript, so the reference names the speaker the
    request names."""
    tagged, untagged = Span("[calm] Fine.", "<|speaker:12|>"), Span("Fine.")
    assert (tagged.speaker_id, untagged.speaker_id, Span("Hi.", "<|speaker:0|>").speaker_id) == (12, 0, 0)
    assert tagged.with_speaker("Hello there.") == "<|speaker:12|>Hello there."
    assert untagged.with_speaker("Hello there.") == "Hello there."


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


def test_inline_speaker_tags_get_their_own_take():
    """Within one text, the spans of each speaker tag share one take, distinct from the spans of another tag
    number; untagged spans and `<|speaker:0|>` spans share the caller speaker's default take, the one a saved voice
    seeds through `keep(model, speaker, take)`. Guards the separate voices of inline speaker tags."""
    takes = Takes()
    seeded = takes.keep("f:drama-3", "host", Take(b"S", "Saved.", None))
    spans = split_spans("Hi. <|speaker:1|>[whisper] Quiet. [shouting] Now! <|speaker:0|>[calm] Fine.")
    for i, span in enumerate(spans):
        takes.keep("f:drama-3", "host", Take(str(i).encode(), span.text, None), span.speaker_id)
    voices = [takes.get("f:drama-3", "host", s.speaker_id) for s in spans]
    assert voices[0] is seeded and voices[3] is seeded
    assert voices[1] is voices[2] and voices[1].wav == b"1" and voices[1] is not seeded
    assert takes.get("f:drama-3", None, 1) is None and takes.get("f:drama-3", "host") is seeded


def test_take_save_keeps_an_existing_folder(tmp_path):
    """`Take.save` writes through a temporary sibling folder and a rename: to a folder that exists already it writes
    nothing, returns None and keeps the existing take, and no temporary folder is left. Guards two commands that
    save one new Fish voice name (docs/ai_models.md, Fish)."""
    codes = torch.zeros(10, 2, dtype=torch.long)
    first = Take(b"A", "Hi.", codes).save(tmp_path / "anna.fish")
    assert first == tmp_path / "anna.fish"
    assert Take(b"B", "Hey.", codes).save(tmp_path / "anna.fish") is None
    assert Take.load(first).wav == b"A"
    assert [p.name for p in tmp_path.iterdir()] == ["anna.fish"]


def test_linked_folder_seeds_when_it_appears(tmp_path):
    """`Takes.link` seeds a voice from its folder at once when the folder exists, else at the first `get` that finds
    it; `loaded` tells such a take from one the process kept; a voice that already has a take keeps it. Guards the
    seed of a Fish voice that another process saved while this one waited for the local-model lock."""
    codes = torch.zeros(10, 2, dtype=torch.long)
    takes = Takes()
    assert takes.link("f:drama-3", "host", tmp_path / "anna.fish") is None
    assert takes.get("f:drama-3", "host") is None
    Take(b"A", "Hi.", codes).save(tmp_path / "anna.fish")
    assert takes.get("f:drama-3", "host").wav == b"A" and takes.loaded("f:drama-3", "host")
    assert takes.get("f:drama-3", "host", 1) is None
    mine = takes.keep("f:drama-3", "guest", Take(b"G", "Hello.", codes))
    takes.link("f:drama-3", "guest", tmp_path / "anna.fish")
    assert takes.get("f:drama-3", "guest") is mine and not takes.loaded("f:drama-3", "guest")
    assert takes.link("f:drama-3", None, tmp_path / "anna.fish").wav == b"A"
    takes.clear()
    assert takes.get("f:drama-3", "host") is None and not takes.loaded("f:drama-3", "host")


def test_take_save_and_load_round_trip(tmp_path):
    """`Take.save` writes `voice.wav`, `voice.txt` and `codes.pt` to a new folder, and `Take.load` reads the
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
