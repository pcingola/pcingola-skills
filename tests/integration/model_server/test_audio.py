"""`POST /v1/audio/speech`, `/v1/audio/music` and `/v1/audio/alignments` of the model server (docs/model_server.md,
Audio) on the tiny models of tests/config.yaml in process: speech through the `openai` SDK (Kokoro and Chatterbox
on the CPU), music and alignment, which the SDK has no call for, through httpx."""

import pytest
import torch

from tests.prereq import requires
from tests.settings_env import kind_model, task_model
from tests.wav import read

SPEECH = task_model("speech")
TEXT = "The heart pumps blood through the body."
TOKENS = "the heart pumps blood through the body"


def test_kokoro_speech(running):
    """`audio.speech.create` on the Kokoro model answers a 24 kHz mono WAV of the text in the voice asked for."""
    wav = read(running.client.audio.speech.create(model=SPEECH, input=TEXT, voice="af_heart",
                                                  response_format="wav").content)
    assert (wav.rate, wav.channels) == (24_000, 1) and wav.seconds > 0.5 and wav.rms > 0


def test_speech_model_lists_its_voices(running):
    """`models.retrieve` of the Kokoro model has `voices`, the voices of its `langs` prefixes read from its voices
    file (more than the default voice); a Chatterbox model without `voices` lists its default voice; the list of
    every model carries no `voices` (docs/model_server.md, Models)."""
    voices = running.client.models.retrieve(SPEECH).voices
    assert "af_heart" in voices and "af_bella" in voices and all(v[:3] in ("af_", "am_", "bf_", "bm_") for v in voices)
    assert running.client.models.retrieve(kind_model("chatterbox")).voices == ["default"]
    assert all(getattr(m, "voices", None) is None for m in running.client.models.list().data)


def test_chatterbox_speech(running):
    """`audio.speech.create` on the Chatterbox model with its built-in voice answers a 24 kHz mono WAV."""
    wav = read(running.client.audio.speech.create(model=kind_model("chatterbox"), input="Hello there.",
                                                  voice="default", response_format="wav").content)
    assert (wav.rate, wav.channels) == (24_000, 1) and wav.seconds > 0.2


def test_speech_refuses_what_local_models_do_not_make(running):
    """An MP3 answer and a request field the model does not take are 400 errors naming the field."""
    import openai

    with pytest.raises(openai.BadRequestError) as e:
        running.client.audio.speech.create(model=SPEECH, input=TEXT, voice="af_heart", response_format="mp3")
    assert e.value.param == "response_format"
    with pytest.raises(openai.BadRequestError) as e:
        running.client.audio.speech.create(model=SPEECH, input=TEXT, voice="af_heart", response_format="wav",
                                           extra_body={"temperature": 0.5})
    assert e.value.param == "temperature"


def test_alignment_of_spoken_text(running):
    """`/v1/audio/alignments` aligns a Kokoro recording against its tokens: one word per token, in order, each
    within the recording and after the previous one."""
    audio = running.client.audio.speech.create(model=SPEECH, input=TEXT, voice="af_heart",
                                               response_format="wav").content
    r = running.http.post("/v1/audio/alignments", data={"model": task_model("align"), "text": TOKENS},
                          files={"file": ("speech.wav", audio, "audio/wav")})
    assert r.status_code == 200, r.text
    out = r.json()
    words = out["words"]
    assert [w["word"] for w in words] == TOKENS.split() and out["object"] == "audio.alignment"
    assert abs(out["duration"] - read(audio).seconds) < 0.01
    assert all(0 <= w["start"] <= w["end"] <= out["duration"] for w in words)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))


@requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
          f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
def test_music(running, tiny_ace_step_folder):
    """`/v1/audio/music` on the tiny ACE-Step pipeline answers a WAV of about `seconds` at 48 kHz; a field the
    music params do not have is a 400."""
    model = task_model("music")
    r = running.http.post("/v1/audio/music", json={"model": model, "prompt": "calm piano", "seconds": 1.0,
                                                   "lyrics": "la la", "seed": 3})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/wav"
    wav = read(r.content)
    assert wav.rate == 48_000 and 0.5 < wav.seconds < 1.5
    bad = running.http.post("/v1/audio/music", json={"model": model, "prompt": "p", "tempo": 120})
    assert bad.status_code == 400 and bad.json()["error"]["param"] == "tempo"
