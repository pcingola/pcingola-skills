"""Chatterbox Turbo through `ai_models.speech` (docs/ai_models.md, Local speech and alignment): the worker in the
environment of the config's `chatterbox` provider, on the CPU, with the built-in voice and with a cloned one. The
provider is the first of kind `chatterbox` in the user's config.yaml (or the file SKILLS_CONFIG names); its model is
`chatterbox-turbo`, its weights in the provider's `dir`, else where media:voiceover keeps them."""

import io
import wave

import numpy as np

from pathlib import Path

from plugin_settings import Plugin

from ai_models import AIModelsError, config, speech
from tests.prereq import requires

MODEL = "chatterbox-turbo"
# The weights directory media:voiceover passes (its plugin data directory's `voiceover/`), for a provider without `dir`.
WEIGHTS = Plugin.of(Path(__file__).resolve().parents[3] / "plugins/media/skills/voiceover").data_dir() / "voiceover"


def provider() -> str | None:
    try:
        providers = config.load().providers
    except AIModelsError:
        return None
    return next((n for n, p in providers.items() if p.kind == "chatterbox"), None)


NAME = provider()


def speak(text: str, **kw) -> bytes:
    return speech.speak(text, weights_dir=WEIGHTS, **kw)


def read(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768, w.getframerate()


@requires(NAME is not None, "config.yaml has no provider of kind chatterbox (setup:settings describes it)")
def test_builtin_and_cloned_voice(tmp_path):
    """The built-in voice gives 24 kHz speech of plausible length; two takes joined (over 5 s) are a reference
    recording the model clones in the same worker; a reference of 5 s or less is refused by the worker, which keeps
    answering."""
    model = f"{NAME}:{MODEL}"
    a, rate = read(speak("The heart pumps blood through the body.", model=model))
    b, _ = read(speak("Count slowly from one to ten, then stop.", model=model))
    assert rate == 24_000 and 1.0 < a.size / rate < 10 and float(np.abs(a).max()) > 0.01
    ref = tmp_path / "ref.wav"
    joined = np.concatenate([a, np.zeros(rate // 2, np.float32), b, np.zeros(rate // 2, np.float32), a])
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((joined * 32767).astype("<i2").tobytes())
    assert joined.size / rate > 5
    c, _ = read(speak("This is a cloned voice.", model=model, voice=str(ref)))
    assert 0.5 < c.size / rate < 10 and float(np.abs(c).max()) > 0.01
    short = tmp_path / "short.wav"
    with wave.open(str(short), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((a[: 2 * rate] * 32767).astype("<i2").tobytes())
    try:
        speak("Too short.", model=model, voice=str(short))
    except AIModelsError as e:
        assert "longer than 5 s" in str(e)
    else:
        raise AssertionError("a reference of 2 s was accepted")
    assert read(speak("Still here.", model=model))[0].size > 0
