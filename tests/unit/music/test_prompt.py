from music_tool.prompt import INSTRUMENTAL, compose, local_lyrics, request, tags
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


def test_request_passes_lyrics():
    """prompt.request sends sung lyrics to Lyria as given and to a local model stripped
    (references: music SKILL.md, `--lyrics`); instrumental sends none to Lyria."""
    song = "[Verse]\nla la\n"
    assert request("pop", song, False, None, local=False) == ("pop.", song)
    assert request("pop", song, False, 90, local=True) == ("pop, 90 bpm", "[Verse]\nla la")
    assert request("pop", None, True, None, local=False) == ("pop. Instrumental only, no vocals.", None)
    assert request("pop", None, True, None, local=True) == ("pop", INSTRUMENTAL)
    with pytest.raises(ValueError):
        request("pop", song, True, None, local=False)
