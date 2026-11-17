"""Real calls to remote speech and music models through `ai_models.speech` and `ai_models.music`, the code paths
that do not go through Pydantic-AI. The models are those of tests/models/config.yaml; `models_config` takes the
api_key and endpoint of each provider from the provider of the same kind in the user's config, and a test fails
when that provider or its key is missing."""

import pytest

from ai_models import config, music, speech
from tests.models.conftest import models_config
from tests.settings_env import MODELS_CONFIG, config_sections
from tests.wav import read

PROVIDERS = config_sections(MODELS_CONFIG)["providers"]
# The remote models of MODELS_CONFIG with a voice (speech) and with `predict` (Lyria music).
SPEECH = [f"{p}:{m}" for p, s in PROVIDERS.items() for m, e in s["models"].items() if "voice" in e]
LYRIA = [f"{p}:{m}" for p, s in PROVIDERS.items() for m, e in s["models"].items() if e.get("predict")]


@pytest.fixture
def use_config(tmp_path):
    """Use the settings file `models_config` writes for a model id; back to the default after the test."""
    yield lambda model_id: config.use(models_config(tmp_path / "config.yaml", model_id))
    config.use(None)


@pytest.mark.timeout(120)
@pytest.mark.parametrize("model", SPEECH)
def test_speech(model, use_config):
    """Each remote speech model (OpenAI SDK `audio.speech` for Azure, `generate_content` with audio output for
    Gemini TTS) answers a short sentence in its configured voice with a 16-bit WAV that has samples."""
    use_config(model)
    assert read(speech.speak("Hello.", model=model)).seconds > 0, model


@pytest.mark.timeout(300)
@pytest.mark.parametrize("model", LYRIA)
def test_lyria(model, use_config):
    """Lyria 2 through the Vertex predict endpoint answers a short prompt with a WAV track."""
    use_config(model)
    assert music.compose("calm solo piano", model=model)[0].audio[:4] == b"RIFF", model
