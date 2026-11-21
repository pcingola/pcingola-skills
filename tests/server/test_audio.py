"""Speech, alignments and music of the deployed server (docs/model_server.md, Speech, Alignments and Music) with its
tiny models, through `ai_models.speech`, `ai_models.align` and `ai_models.music`."""

import pytest

from ai_models import align, music, speech
from ai_models.served_aligner import ServedAligner
from tests.server.conftest import TIMEOUT_SECONDS, model, task
from tests.wav import read, reference

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)
TEXT = "The heart pumps blood."
TOKENS = ["the", "heart", "pumps", "blood"]
FISH_RATE = 44_100
SPEECH_RATE = 24_000  # Kokoro and Chatterbox


def test_kokoro_speaks_in_another_voice():
    """`speech.speak` on tasks.speech (Kokoro) in a voice other than the default, at a speed Kokoro takes, answers
    a 24 kHz mono WAV with sound."""
    assert speech.check(speed=1.5).default_voice != "af_bella"
    wav = read(speech.speak(TEXT, voice="af_bella", speed=1.5))
    assert (wav.rate, wav.channels) == (SPEECH_RATE, 1) and wav.seconds > 0.3 and wav.rms > 0


def test_chatterbox_clones_a_reference_sent_in_the_request(tmp_path):
    """`speech.speak` of the Chatterbox model with a recording on this machine as the voice sends its bytes in
    `reference_audio`, and the server speaks in that voice: a 24 kHz WAV with sound."""
    m = model("chatterbox-turbo")
    assert speech.check(m).traits.clones is True
    ref = tmp_path / "narrator.wav"
    ref.write_bytes(reference(speech.speak(TEXT)))
    wav = read(speech.speak("A cloned voice.", model=m, voice=str(ref)))
    assert wav.rate == SPEECH_RATE and wav.seconds > 0.2 and wav.rms > 0


def test_fish_speaks_with_a_speaker():
    """`speech.speak` of the Fish model with `speaker` (an extra field of the request) answers a 44.1 kHz mono
    WAV."""
    wav = read(speech.speak(TEXT, model=model("drama-3-tiny"), speaker="ann"))
    assert (wav.rate, wav.channels) == (FISH_RATE, 1) and wav.seconds > 0


def test_alignment():
    """`align.aligner` on tasks.align is a `ServedAligner`: `POST /v1/audio/alignments` of a recording of the
    server's speech answers one (start, end) per token, in order, within the recording."""
    a = align.aligner()
    assert isinstance(a, ServedAligner)
    wav = read(speech.speak(TEXT))
    spans = a.align(wav.samples[:, 0], wav.rate, TOKENS)
    assert len(spans) == len(TOKENS)
    assert all(0 <= s <= e <= wav.seconds + 0.01 for s, e in spans)
    assert all(spans[i][1] <= spans[i + 1][0] + 1e-6 for i in range(len(spans) - 1))


def test_music():
    """`music.compose` on tasks.music (`POST /v1/audio/music`, tiny ACE-Step) with lyrics and a seed answers one
    48 kHz WAV of about the `seconds` asked for."""
    assert music.model_api(task("music")) == "server"
    [track] = music.compose("calm piano", seconds=1.0, lyrics="la la", seed=3)
    wav = read(track.audio)
    assert wav.rate == 48_000 and 0.5 < wav.seconds < 1.5
