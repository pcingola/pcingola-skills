"""Speech, alignment and music of `ai_models` on the model server's tiny local models through a provider of kind
`openai` (`ai_models.served`; docs/ai_models.md, Provider kinds): the model attributes come from the server's
`GET /v1/models/{id}`."""

import pytest

from ai_models import AIModelsError, ConfigError, align, music, speech
from ai_models.served_aligner import ServedAligner
from tests.integration.model_server_client.conftest import client_id
from tests.settings_env import kind_model
from tests.wav import read

TEXT = "The heart pumps blood."
TOKENS = ["the", "heart", "pumps", "blood"]


def test_speech_takes_the_traits_of_the_served_kind(client):
    """`speech.check` of the server's Kokoro model has Kokoro's speed range and no instructions, and its default
    voice is the server entry's `voice`; `speech.voices` is the server's list, with voices besides the default;
    `speak` answers a 24 kHz WAV at a speed Kokoro takes, in a listed voice other than the default."""
    m = speech.check(speed=1.5)
    assert (m.traits.speed, m.instructions, m.default_voice) == ((0.5, 2.0), False, "af_heart")
    voices = speech.voices()
    assert "af_heart" in voices and "af_bella" in voices
    other = read(speech.speak(TEXT, voice="af_bella"))
    assert other.rate == 24_000 and other.seconds > 0.3
    with pytest.raises(AIModelsError, match="speed must be between 0.5 and 2"):
        speech.check(speed=3.0)
    wav = read(speech.speak(TEXT, speed=1.5))
    assert (wav.rate, wav.channels) == (24_000, 1) and wav.seconds > 0.3


def test_served_chatterbox_does_not_clone(client):
    """A served Chatterbox model speaks in its default voice and does not take a reference recording, which
    would be a path on the server's machine."""
    model = f"srv:{kind_model('chatterbox')}"
    assert speech.check(model).traits.clones is False
    wav = read(speech.speak("Hello there.", model=model))
    assert wav.rate == 24_000 and wav.seconds > 0.2


def test_aligner_of_the_server(client):
    """`align.aligner` of tasks.align is a `ServedAligner`; it aligns a recording of the server's speech model
    against its tokens, one (start, end) per token, in order, within the recording."""
    a = align.aligner()
    assert isinstance(a, ServedAligner)
    wav = read(speech.speak(TEXT))
    spans = a.align(wav.samples[:, 0], wav.rate, TOKENS)
    assert len(spans) == len(TOKENS)
    assert all(0 <= s <= e <= wav.seconds + 0.01 for s, e in spans)
    assert all(spans[i][1] <= spans[i + 1][0] + 1e-6 for i in range(len(spans) - 1))


def test_aligner_refuses_a_model_of_another_role(client):
    """A speech model of the server named as the aligner is a `ConfigError` naming its role."""
    with pytest.raises(ConfigError, match="speech model of its server"):
        align.aligner(client_id("speech"))


def test_music(client, tiny_ace_step_folder):
    """`music.compose` on tasks.music, the server's tiny ACE-Step model, answers one 48 kHz WAV of about
    `seconds`, with lyrics (the server entry has `lyrics_arg`); it takes the options of a diffusers model."""
    model = client_id("music")
    assert music.model_api(model) == "server" and "seed" in music.takes(model)
    assert music.min_crest_db(model) is None
    [track] = music.compose("calm piano", seconds=1.0, lyrics="la la", seed=3)
    wav = read(track.audio)
    assert wav.rate == 48_000 and 0.5 < wav.seconds < 1.5
    with pytest.raises(AIModelsError, match="does not take images"):
        music.compose("calm piano", images=[(b"x", "image/png")])
