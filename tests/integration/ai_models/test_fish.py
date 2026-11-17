"""Fish through `ai_models.speech` (`ai_models.fish`) on the tiny random-weight Drama 3 checkpoint of the `fish`
provider of tests/config.yaml (`tests/tiny_fish.py`), loaded in this process on the GPU. Random weights speak noise
and never end on their own, so each request runs to the model's `max_frames`."""

import pytest

from ai_models import config, speech
from tests.settings_env import TEST_CONFIG, kind_entry, kind_model
from tests.wav import read

MODEL = kind_model("fish")
MAX_FRAMES = kind_entry("fish")["max_frames"]
HOP = 2048  # samples per frame of the Drama 3 codec at 44.1 kHz


@pytest.fixture(autouse=True)
def _config(tiny_fish_folder):
    """TEST_CONFIG in use for the test, with the tiny checkpoint built."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def test_sentence_and_two_tags():
    """One sentence gives one request: a 16-bit mono 44.1 kHz WAV of at most `max_frames` frames. A text with two
    style tags is cut at the tags into two requests (`ai_models.fish_span`), so its WAV is longer than one request
    can be."""
    one = read(speech.speak("The heart pumps blood through the body.", model=MODEL))
    assert (one.rate, one.channels) == (44_100, 1)
    assert 0 < one.samples.shape[0] <= MAX_FRAMES * HOP
    two = read(speech.speak("[whisper] Someone is there. [laughing] Only the cat!", model=MODEL))
    assert (two.rate, two.channels) == (44_100, 1)
    assert MAX_FRAMES * HOP < two.samples.shape[0] <= 2 * MAX_FRAMES * HOP
