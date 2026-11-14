"""Backend choice, Kokoro voices, and the `speech` backend's config handling and audio decoding (no model call)."""

import io
import wave

import numpy as np
import pytest

from tests.unit.voiceover.cli_run import voiceover
from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python
from voiceover_tool.backends import KokoroBackend, get_backend
from voiceover_tool.speech import decode
from voiceover_tool.timing import build_timing


def test_unknown_backend_refused():
    with pytest.raises(ValueError, match="unknown backend 'nope'; available: chatterbox, kokoro, speech"):
        get_backend("nope")


def test_kokoro_lang_and_style(tmp_path):
    """A Kokoro voice's espeak language comes from the prefixes of the setting VOICEOVER_KOKORO_LANGS; a voice of
    no listed prefix is a ValueError, a malformed setting an error naming it, and Kokoro takes no style."""
    config = write_config(tmp_path / "config.yaml", {"VOICEOVER_KOKORO_LANGS": "af_=en-us, bm_=en-gb"})
    imports = "from voiceover_tool.backends import kokoro_lang"
    env = child_env(SKILLS_CONFIG=str(config))
    assert py_value(imports, "[kokoro_lang(v) for v in ('af_heart', 'bm_george')]", env) == ["en-us", "en-gb"]
    done = run_python(f"{imports}\nkokoro_lang('ff_siwis')", env)
    assert "ValueError" in done.stderr and "VOICEOVER_KOKORO_LANGS" in done.stderr
    bad = write_config(tmp_path / "bad.yaml", {"VOICEOVER_KOKORO_LANGS": "af_en-us"})
    done = run_python(f"{imports}\nkokoro_lang('af_heart')", child_env(SKILLS_CONFIG=str(bad)))
    assert done.returncode == 1 and "VOICEOVER_KOKORO_LANGS" in done.stderr and "prefix=language" in done.stderr
    with pytest.raises(ValueError):
        KokoroBackend(style="calm")


def test_decode_wav_and_raw_pcm():
    """A stereo 16 kHz WAV is mixed to mono at its rate; bytes without a RIFF header are 24 kHz PCM."""
    pcm = np.array([[16384, 0], [-16384, 0]], dtype="<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    samples, rate = decode(buf.getvalue())
    assert rate == 16000 and np.allclose(samples, [0.25, -0.25])
    samples, rate = decode(np.array([16384, -32768], dtype="<i2").tobytes())
    assert rate == 24000 and np.allclose(samples, [0.5, -1.0])


def test_speech_backend_from_config(tmp_path):
    """The `speech` backend takes the config's `speech` model; `voices` lists the setting VOICEOVER_SPEECH_VOICES
    with VOICEOVER_SPEECH_VOICE as default; no `speech` task is an error; a speed outside 0.25 to 4, or any speed other than 1 with
    Gemini TTS, is refused before any request."""
    config = tmp_path / "config.yaml"
    config.write_text("providers:\n  oai: {kind: openai, base_url: http://127.0.0.1:1/v1}\nmodels: {}\n")
    p = voiceover("voices", "--backend", "speech", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "no model for task 'speech'" in p.stderr

    voice_settings = "settings: {VOICEOVER_SPEECH_VOICE: two, VOICEOVER_SPEECH_VOICES: 'one,two'}\n"
    config.write_text("providers:\n  oai: {kind: openai, base_url: http://127.0.0.1:1/v1}\n"
                      "models: {speech: 'oai:tts-1'}\n" + voice_settings)
    p = voiceover("voices", "--backend", "speech", SKILLS_CONFIG=str(config))
    assert p.returncode == 0, p.stderr
    assert p.stdout.split("\n")[:2] == ["one", "two  (default)"]

    script = tmp_path / "s.txt"
    script.write_text("Hello there.\n")
    synth = ("synth", "--backend", "speech", "--script", str(script), "--out-dir", str(tmp_path / "o"), "--no-align")
    p = voiceover(*synth, "--speed", "5", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "between 0.25 and 4" in p.stderr

    config.write_text("providers:\n  g: {kind: google}\nmodels: {speech: 'g:gemini-3.8-flash-tts'}\n" + voice_settings)
    p = voiceover(*synth, "--speed", "1.2", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "no speed setting" in p.stderr


def test_timing_model_and_style_only_when_set():
    kw = dict(audio="a.wav", sample_rate=24000, duration=1.0, backend="b", voice="v", speed=1.0, sentences=[])
    assert "model" not in build_timing(**kw) and "style" not in build_timing(**kw)
    t = build_timing(model="m", style="calm", **kw)
    assert (t["model"], t["style"]) == ("m", "calm")
