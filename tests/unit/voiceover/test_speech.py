"""The narrator: the speech model of the config (or `--model`), its default voice and voices, the speed and style it
refuses before any request, and audio decoding (no model call)."""

import io
import wave

import numpy as np

from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python
from tests.unit.voiceover.cli_run import voiceover
from voiceover_tool.speech import decode
from voiceover_tool.timing import build_timing

OAI = {"kind": "openai", "base_url": "http://127.0.0.1:1/v1"}


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


def test_voices_of_the_speech_model_and_of_another(tmp_path):
    """`voices` lists the provider's `voices` with its `voice` marked default; `--model` lists that model's voices,
    the kind's default voice without a `voice`; no `speech` task is an error naming it."""
    config = write_config(tmp_path / "config.yaml", providers={"oai": {**OAI, "voice": "two", "voices": ["one", "two"]},
                                                               "g": {"kind": "google"}}, models={})
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "no model for task 'speech'" in p.stderr
    config = write_config(tmp_path / "config.yaml", providers={"oai": {**OAI, "voice": "two", "voices": ["one", "two"]},
                                                               "g": {"kind": "google"}}, models={"speech": "oai:tts-1"})
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 0 and p.stdout.splitlines() == ["one", "two  (default)"], p.stderr
    p = voiceover("voices", "--model", "g:gemini-tts", SKILLS_CONFIG=str(config))
    assert p.returncode == 0 and p.stdout.splitlines() == ["Kore  (default)"], p.stderr


def test_speed_and_style_refused_before_any_request(tmp_path):
    """A speed outside the kind's range, a speed with a model that has none, and a style with a model that takes
    none are refused before any request (the OpenAI provider points at a closed
    port, the Kokoro files at a closed port); a model of a provider kind
    without speech models is refused."""
    config = write_config(tmp_path / "config.yaml",
                          providers={"oai": OAI, "g": {"kind": "google"},
                                     "k": {"kind": "kokoro", "model_url": "http://127.0.0.1:1/m.onnx",
                                           "voices_url": "http://127.0.0.1:1/v.bin", "langs": {"af_": "en-us"}},
                                     "local": {"kind": "diffusers"}},
                          models={"speech": "oai:tts-1"})
    script = tmp_path / "s.txt"
    script.write_text("Hello there.\n")
    synth = ("synth", "--script", str(script), "--out-dir", str(tmp_path / "o"), "--no-align")
    p = voiceover(*synth, "--speed", "5", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "between 0.25 and 4" in p.stderr, p.stderr
    p = voiceover(*synth, "--model", "g:gemini-tts", "--speed", "1.2", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "no speed setting" in p.stderr, p.stderr
    p = voiceover(*synth, "--model", "k:kokoro-v1.0", "--style", "calm", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "takes no instructions" in p.stderr, p.stderr
    p = voiceover(*synth, "--model", "local:flux", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "has no speech models" in p.stderr, p.stderr
    assert not (tmp_path / "o").exists()


def test_timing_records_the_model_and_style_only_when_set():
    kw = dict(audio="a.wav", sample_rate=24000, duration=1.0, model="k:kokoro-v1.0", voice="v", speed=1.0,
              sentences=[])
    assert build_timing(**kw)["model"] == "k:kokoro-v1.0" and "style" not in build_timing(**kw)
    assert build_timing(style="calm", **kw)["style"] == "calm"


def test_lines_as_the_model_takes_them(tmp_path):
    """`Narrator.lines` reads speakers and inline tags for a model that takes tags (vllm-omni), a leading `[style]`
    for one that takes styles (OpenAI), and literal text without tags for one that takes neither (Kokoro)."""
    config = write_config(tmp_path / "config.yaml",
                          providers={"oai": OAI, "k": {"kind": "kokoro", "langs": {"af_": "en-us"}},
                                     "f": {"kind": "vllm-omni", "python": "/nonexistent"}},
                          models={"speech": "oai:tts-1"})
    imports = "from voiceover_tool.speech import Narrator"
    lines = ["[whisper] Keep it quiet.", "@guest Well [laughs] maybe that's fair."]
    expr = "[[l.text, l.said, l.style, l.speaker] for l in Narrator({m}).lines({lines!r})]"
    env = child_env(SKILLS_CONFIG=str(config))
    assert py_value(imports, expr.format(m="", lines=lines[:1]), env) == [
        ["Keep it quiet.", "Keep it quiet.", "whisper", None]]
    done = run_python(f"{imports}\nNarrator().lines({lines[1:]!r})", env)
    assert "would speak aloud" in done.stderr
    plain = ["Keep it quiet.", "Hello @ noon."]
    assert py_value(imports, expr.format(m="'k:kokoro-v1.0'", lines=plain), env) == [[l, l, None, None] for l in plain]
    assert py_value(imports, expr.format(m="'f:drama-3'", lines=lines), env) == [
        ["Keep it quiet.", "[whisper] Keep it quiet.", None, None],
        ["Well maybe that's fair.", "Well [laughs] maybe that's fair.", None, "guest"]]


def test_speakers_and_params_refused_by_a_model_that_takes_none(tmp_path):
    """`--speaker` with a model that takes no inline tags and `--param` with one that takes no request fields are
    refused before any request; a `--param` that is not KEY=VALUE is refused; a line of only tags is refused."""
    config = write_config(tmp_path / "config.yaml",
                          providers={"k": {"kind": "kokoro", "langs": {"af_": "en-us"}},
                                     "f": {"kind": "vllm-omni", "python": "/nonexistent"}},
                          models={"speech": "k:kokoro-v1.0"})
    script = tmp_path / "s.txt"
    script.write_text("@host Hello.\n")
    synth = ("synth", "--script", str(script), "--out-dir", str(tmp_path / "o"), "--no-align")
    p = voiceover(*synth, "--speaker", "host=alice", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "takes no speakers" in p.stderr, p.stderr
    p = voiceover(*synth, "--param", "seed=7", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "takes no request parameters" in p.stderr, p.stderr
    p = voiceover(*synth, "--model", "f:drama-3", "--param", "seed", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "expected NAME=VALUE" in p.stderr, p.stderr
    script.write_text("@host [laughs]\n")
    p = voiceover(*synth, "--model", "f:drama-3", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "has only tags" in p.stderr, p.stderr
    script.write_text("Hello [laughs] there.\n")
    p = voiceover(*synth, SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "would speak aloud" in p.stderr, p.stderr
    assert not (tmp_path / "o").exists()


def test_speakers_checked_before_any_request(tmp_path):
    """With a model that takes tags, a `--speaker` name that is not a speaker name or that no line uses, an `@Name`
    line, and a speaker recording without transcript are refused before the server starts (its python does not
    exist, so any start would fail otherwise); a missing narrator recording too. Guards a typo found after a 5 min
    model load."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "anna.wav").write_bytes(b"RIFF")
    config = write_config(tmp_path / "config.yaml", {"VOICEOVER_VOICES_DIR": str(voices_dir)},
                          providers={"f": {"kind": "vllm-omni", "python": "/nonexistent"}},
                          models={"speech": "f:drama-3"})
    script = tmp_path / "s.txt"
    script.write_text("@host Hello.\n@guest Hi.\n")
    synth = ("synth", "--script", str(script), "--out-dir", str(tmp_path / "o"), "--no-align")
    for args, message in [(("--speaker", "Host=anna"), "lowercase letters"),
                          (("--speaker", "hots=anna"), "no `@name` line of the script has that speaker"),
                          (("--speaker", "host=anna"), "has no transcript"),
                          (("--speaker", "host=bob"), "unknown voice 'bob'"),
                          (("--voice", "bob"), "unknown voice 'bob'")]:
        p = voiceover(*synth, *args, SKILLS_CONFIG=str(config))
        assert p.returncode == 1 and message in p.stderr, (args, p.stderr)
    script.write_text("@Host Hello.\n")
    p = voiceover(*synth, SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "lowercase letters" in p.stderr, p.stderr
    assert not (tmp_path / "o").exists()


def test_first_takes_per_speaker_written(tmp_path):
    """`Narrator.first_takes` gives the first `default` take of the narrator and of each made-up speaker that
    `omni.keep_take` kept, and `write_takes` writes them as `voice.wav` and `voice-<name>.wav` with transcripts."""
    config = write_config(tmp_path / "config.yaml", providers={"f": {"kind": "vllm-omni", "python": "/nonexistent"}},
                          models={"speech": "f:drama-3"})
    code = f"""
from ai_models import omni
from voiceover_tool.cli import write_takes
from voiceover_tool.speech import Narrator
n = Narrator()
lines = n.lines(["Hi.", "@guest Hello.", "@host Hey.", "@guest Again."])
n.prepare(lines, "default")
omni.keep_take("f", None, "default", b"N", "Hi.")
omni.keep_take("f", "guest", "default", b"G", "Hello.")
omni.keep_take("f", "guest", "default", b"G2", "Again.")
omni.keep_take("f", "host", "/some/ref.wav", b"H", "Hey.")
print(sorted(p.name for p in write_takes(__import__("pathlib").Path({str(tmp_path)!r}), n.first_takes())))
"""
    done = run_python(code, child_env(SKILLS_CONFIG=str(config)))
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["['voice-guest.wav',", "'voice.wav']"]
    assert "made-up voices" in done.stderr and "guest, host" in done.stderr
    assert (tmp_path / "voice-guest.wav").read_bytes() == b"G" and (tmp_path / "voice-guest.txt").read_text() == "Hello.\n"


def test_params_parse_as_json_else_string():
    """`--param` values that parse as JSON are sent as that value, others as strings."""
    from voiceover_tool.cli import _params

    assert _params(["seed=7", 'extra_params={"temperature": 0.8}', "language=English"]) == {
        "seed": 7, "extra_params": {"temperature": 0.8}, "language": "English"}


def test_earlier_model_settings_refused(tmp_path):
    """A `VOICEOVER_*` setting other than VOICEOVER_VOICES_DIR stops every command with one message naming the
    template entries that replace it; with VOICEOVER_MODEL_DIR, the message gives it as the providers' `dir` and its
    voices/ as VOICEOVER_VOICES_DIR."""
    config = write_config(tmp_path / "config.yaml", {"VOICEOVER_KOKORO_VOICE": "af_heart",
                                                     "VOICEOVER_MODEL_DIR": "/old/voiceover",
                                                     "VOICEOVER_VOICES_DIR": "/old/voiceover/voices"},
                          providers={"oai": OAI}, models={"speech": "oai:tts-1"})
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "Traceback" not in p.stderr, p.stderr
    for part in ("VOICEOVER_KOKORO_VOICE, VOICEOVER_MODEL_DIR", "`kokoro` and `torchaudio`", "`chatterbox`",
                 "`models.speech` and `models.align`", "config.example.yaml", "`dir: /old/voiceover`",
                 "VOICEOVER_VOICES_DIR: /old/voiceover/voices"):
        assert part in p.stderr, (part, p.stderr)
    config = write_config(tmp_path / "ok.yaml", {"VOICEOVER_VOICES_DIR": str(tmp_path)}, providers={"oai": OAI},
                          models={"speech": "oai:tts-1"})
    assert voiceover("voices", SKILLS_CONFIG=str(config)).returncode == 0
