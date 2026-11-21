"""`POST /v1/audio/speech` of the model server on the tiny random-weight Drama 3 checkpoint of the `fish` provider of
tests/config.yaml (`tests/tiny_fish.py`), loaded in the server's process on an NVIDIA GPU, through the `openai` SDK.
Random weights never end on their own, so each request runs to the model's `max_frames`."""

import torch

from tests.prereq import requires
from tests.settings_env import kind_entry, kind_model
from tests.wav import read

MODEL = kind_model("fish")
MAX_FRAMES = kind_entry("fish")["max_frames"]
HOP = 2048  # samples per frame of the Drama 3 codec at 44.1 kHz


@requires(torch.cuda.is_available(), "fish-speech runs only on an NVIDIA GPU (CUDA)")
def test_fish_speech_with_speaker(running, request):
    """A fish model's speech is a 16-bit mono 44.1 kHz WAV of at most `max_frames` frames; `speaker`, a field
    outside the OpenAI params, reaches the model (`ai_models.fish`), which keeps a first take for that speaker."""
    from ai_models import fish

    request.getfixturevalue("tiny_fish_folder")  # after the CUDA check: it builds from the full checkpoint
    audio = running.client.audio.speech.create(model=MODEL, input="The heart pumps blood.", voice="default",
                                               response_format="wav", extra_body={"speaker": "ann"}).content
    wav = read(audio)
    assert (wav.rate, wav.channels) == (44_100, 1) and 0 < wav.samples.shape[0] <= MAX_FRAMES * HOP
    assert fish.takes.get(MODEL, "ann") is not None
