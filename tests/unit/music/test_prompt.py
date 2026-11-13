from music_tool.prompt import INSTRUMENTAL, compose, local_lyrics, tags
import pytest


def test_compose():
    """prompt.compose ends a bare prompt with a period and appends tempo, then instrumental."""
    assert compose("calm piano") == "calm piano."
    assert compose("calm piano!") == "calm piano!"
    assert compose("lo-fi hip hop", instrumental=True, bpm=80) == \
        "lo-fi hip hop. Tempo: 80 BPM. Instrumental only, no vocals."


def test_local_prompt_and_lyrics():
    """ACE-Step gets the tempo as a tag and `[instrumental]` for no vocals."""
    assert tags("synthwave, dreamy.", 110) == "synthwave, dreamy, 110 bpm"
    assert local_lyrics(None, True) == INSTRUMENTAL
    assert local_lyrics("  [Verse]\nla\n") == "[Verse]\nla"
    assert local_lyrics("  ") is None
    with pytest.raises(ValueError):
        local_lyrics("la", True)
