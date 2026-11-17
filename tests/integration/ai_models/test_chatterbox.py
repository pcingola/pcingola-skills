"""Chatterbox Turbo through `ai_models.speech` (docs/ai_models.md, Local speech and alignment): the model of the
`chatterbox` provider of tests/config.yaml, loaded in this process on the CPU, with the built-in voice and with a
cloned one."""

import io
import wave

import numpy as np
import pytest

from ai_models import AIModelsError, config, speech
from tests.settings_env import TEST_CONFIG, kind_model

MODEL = kind_model("chatterbox")


@pytest.fixture(autouse=True)
def _config():
    """TEST_CONFIG in use for the test."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def speak(text: str, **kw) -> tuple[np.ndarray, int]:
    """The samples (float in [-1, 1]) and the rate of `text` spoken by MODEL."""
    with wave.open(io.BytesIO(speech.speak(text, model=MODEL, **kw))) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768, w.getframerate()


def write_wav(path, samples: np.ndarray, rate: int) -> str:
    """`samples` written to `path` as a 16-bit mono WAV file; its path as a string."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((samples * 32767).astype("<i2").tobytes())
    return str(path)


def test_builtin_and_cloned_voice(tmp_path):
    """The built-in voice gives 24 kHz speech of plausible length; that take three times (over 5 s) is a reference
    recording the loaded model clones; a reference of 5 s or less is refused; the model then speaks in the built-in
    voice again."""
    a, rate = speak("The heart pumps blood through the body.")
    assert rate == 24_000 and 1.0 < a.size / rate < 10 and float(np.abs(a).max()) > 0.01
    gap = np.zeros(rate // 2, np.float32)
    joined = np.concatenate([a, gap, a, gap, a])
    assert joined.size / rate > 5
    c, _ = speak("This is a cloned voice.", voice=write_wav(tmp_path / "ref.wav", joined, rate))
    assert 0.5 < c.size / rate < 10 and float(np.abs(c).max()) > 0.01
    with pytest.raises(AIModelsError, match="longer than 5 s"):
        speak("Too short.", voice=write_wav(tmp_path / "short.wav", a[: 2 * rate], rate))
    assert speak("Still here.")[0].size > 0
