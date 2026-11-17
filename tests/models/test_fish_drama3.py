"""Fish Audio Drama 3 through `ai_models.speech` (`ai_models.fish`): the model of the `fish` provider of
tests/models/config.yaml, loaded once in this process on the GPU (about 4 minutes, 44 GB at its peak).

Each request must end on the model's end of speech, not on fish-speech's token cap: fish-speech logs the warning
`Reached max_new_tokens before EOS` for a request that ran to the cap. One sentence gives a few seconds of speech.
A text with two style tags is cut at the tags (`ai_models.fish_span`), one request per tag; in one request Drama 3
speaks it and then runs to the cap on near-silence. Each answer is kept as `<test id>.wav` in pytest's temporary
folder of the test, to listen to.
"""

import pytest
from loguru import logger

from ai_models import config, local, speech
from tests.models.conftest import models_config
from tests.settings_env import MODELS_CONFIG, kind_model
from tests.wav import read

MODEL = kind_model("fish", MODELS_CONFIG)
CAP_WARNING = "Reached max_new_tokens"

pytestmark = pytest.mark.timeout(900)

TEXTS = {
    "en": "The lights of the harbour come on one by one as night falls.",
    "es": "Las luces del puerto se encienden una por una mientras cae la noche.",
    "fr": "Les lumières du port s'allument une à une à la tombée de la nuit.",
    "two_tags": "[whisper] I think someone is standing right behind the door. [laughing] Oh, it is only the cat!",
}


@pytest.fixture(scope="module")
def drama3(tmp_path_factory):
    """The settings of MODEL (`models_config`) in use and MODEL loaded by a first sentence, which becomes the
    narrator's reference take for the tests; the model is unloaded after the module."""
    config.use(models_config(tmp_path_factory.mktemp("settings") / "config.yaml", MODEL))
    speech.speak("Hello, this is the narrator of these tests.", model=MODEL)
    yield
    local.unload()
    config.use(None)


@pytest.fixture
def cap_warnings():
    """The messages of fish-speech's token-cap warnings logged during the test."""
    seen: list[str] = []
    sink = logger.add(lambda m: seen.append(str(m)), level="WARNING", filter=lambda r: CAP_WARNING in r["message"])
    yield seen
    logger.remove(sink)


@pytest.mark.parametrize("name", TEXTS)
def test_speech_ends_on_eos(name, drama3, cap_warnings, tmp_path):
    """English, Spanish, French and a two-tag text each end on the model's end of speech, with 1.5 to 8 s of
    audible mono 44.1 kHz speech per sentence (two sentences for the two-tag text)."""
    data = speech.speak(TEXTS[name], model=MODEL)
    (tmp_path / f"{name}.wav").write_bytes(data)
    w = read(data)
    sentences = 2 if name == "two_tags" else 1
    assert not cap_warnings, f"{name}: a request ran to the token cap: {cap_warnings}"
    assert (w.rate, w.channels) == (44_100, 1)
    assert 1.5 * sentences < w.seconds < 8 * sentences, f"{name}: {w.seconds:.1f} s"
    assert 0.02 < w.rms < 0.5, f"{name}: RMS {w.rms:.3f}"
