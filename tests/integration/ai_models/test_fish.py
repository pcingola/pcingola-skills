"""Fish through `ai_models.speech` (`ai_models.fish`) on the tiny random-weight Drama 3 checkpoint of the `fish`
provider of tests/config.yaml (`tests/tiny_fish.py`), loaded in this process on the GPU. Random weights speak noise
and never end on their own, so each request runs to the model's `max_frames`. The class setup runs every synthesis
with one load of the model, before the autouse unload of `tests/integration/conftest.py` runs after the first test."""

from types import SimpleNamespace

import pytest

from ai_models import fish, speech
from tests.settings_env import TEST_CONFIG, kind_entry, kind_model, use_settings
from tests.wav import read

MODEL = kind_model("fish")
MAX_FRAMES = kind_entry("fish")["max_frames"]
HOP = 2048  # samples per frame of the Drama 3 codec at 44.1 kHz


@pytest.fixture(scope="class")
def spoken(tiny_fish_folder) -> SimpleNamespace:
    """With TEST_CONFIG in use: the WAV of one sentence (`one`), of a text with two style tags (`two`), and, after
    `fish.takes` is cleared, of a text with an inline `<|speaker:1|>` tag (`tagged_wav`) with the untagged take
    (`narrator`) and the `<|speaker:1|>` take (`tagged`) right after it."""
    with use_settings(TEST_CONFIG):
        one = read(speech.speak("The heart pumps blood through the body.", model=MODEL))
        two = read(speech.speak("[whisper] Someone is there. [laughing] Only the cat!", model=MODEL))
        fish.takes.clear()
        tagged_wav = read(speech.speak("Hello. <|speaker:1|>[whisper] Someone is there. [laughing] Only the cat!",
                                       model=MODEL))
        narrator, tagged = fish.takes.get(MODEL), fish.takes.get(MODEL, None, 1)
    return SimpleNamespace(one=one, two=two, tagged_wav=tagged_wav, narrator=narrator, tagged=tagged)


class TestFish:
    def test_sentence_and_two_tags(self, spoken):
        """One sentence gives one request: a 16-bit mono 44.1 kHz WAV of at most `max_frames` frames. A text with
        two style tags is cut at the tags into two requests (`ai_models.fish_span`), so its WAV is longer than one
        request can be."""
        assert (spoken.one.rate, spoken.one.channels) == (44_100, 1)
        assert 0 < spoken.one.samples.shape[0] <= MAX_FRAMES * HOP
        assert (spoken.two.rate, spoken.two.channels) == (44_100, 1)
        assert MAX_FRAMES * HOP < spoken.two.samples.shape[0] <= 2 * MAX_FRAMES * HOP

    def test_inline_speaker_tag_has_its_own_reference(self, spoken):
        """A `<|speaker:1|>` span gets a take of its own, distinct from the untagged span's, and the next
        `<|speaker:1|>` span gets that take as reference, its transcript behind the same speaker tag, which
        fish-speech's prompt builder accepts. Guards the separate voices of inline speaker tags
        (`ai_models.fish_takes`)."""
        assert 2 * MAX_FRAMES * HOP < spoken.tagged_wav.samples.shape[0] <= 3 * MAX_FRAMES * HOP
        narrator, tagged = spoken.narrator, spoken.tagged
        assert narrator is not None and tagged is not None and tagged is not narrator
        assert tagged.text == "[whisper] Someone is there."
