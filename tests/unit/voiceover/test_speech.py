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
GOOGLE = {"kind": "google", "api_key": "k"}
# A fish provider whose repository does not exist; the tests stop before any load.
FISH = {"kind": "fish", "models": {"drama-3": {"repo": "x/drama-3"}}}
KOKORO = {"kind": "kokoro", "models": {"kokoro-v1.0": {"model_url": "http://127.0.0.1:1/m.onnx",
                                                       "voices_url": "http://127.0.0.1:1/v.bin",
                                                       "langs": {"af_": "en-us"}}}}
OAI_VOICES = {**OAI, "models": {"tts-1": {"voice": "two", "voices": ["one", "two"]}}}


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
    """`voices` lists the model entry's `voices` with its `voice` marked default; `--model` lists that model's
    voices, the kind's default voice without a `voice`; no `speech` task is an error naming it."""
    config = write_config(tmp_path / "config.yaml", providers={"oai": OAI_VOICES, "g": GOOGLE}, tasks={})
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "no model for task 'speech'" in p.stderr
    config = write_config(tmp_path / "config.yaml", providers={"oai": OAI_VOICES, "g": GOOGLE},
                          tasks={"speech": "oai:tts-1"})
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
                          providers={"oai": OAI, "g": GOOGLE, "k": KOKORO,
                                     "local": {"kind": "diffusers", "models": {"flux": {"repo": "r"}}}},
                          tasks={"speech": "oai:tts-1"})
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
    assert p.returncode == 1 and "task speech takes kinds" in p.stderr, p.stderr
    assert not (tmp_path / "o").exists()


def test_timing_records_the_model_and_style_only_when_set():
    kw = dict(audio="a.wav", sample_rate=24000, duration=1.0, model="k:kokoro-v1.0", voice="v", speed=1.0,
              sentences=[])
    assert build_timing(**kw)["model"] == "k:kokoro-v1.0" and "style" not in build_timing(**kw)
    assert build_timing(style="calm", **kw)["style"] == "calm"


def test_lines_as_the_model_takes_them(tmp_path):
    """`Narrator.lines` reads speakers and inline tags for a model that takes tags (fish), a leading `[style]`
    for one that takes styles (OpenAI), and literal text without tags for one that takes neither (Kokoro)."""
    config = write_config(tmp_path / "config.yaml",
                          providers={"oai": OAI, "k": KOKORO,
                                     "f": FISH},
                          tasks={"speech": "oai:tts-1"})
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
                          providers={"k": KOKORO,
                                     "f": FISH},
                          tasks={"speech": "k:kokoro-v1.0"})
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
    """With a fish model, a `--speaker` name that is not a speaker name or that no line uses, an `@Name` line, and a
    recording or a voice name with other characters for a speaker or the narrator are refused before the model loads
    (its repository does not exist, so a load would fail otherwise). Guards a typo found after a 4 min model load."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "anna.wav").write_bytes(b"RIFF")
    config = write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices_dir)},
                          providers={"f": FISH},
                          tasks={"speech": "f:drama-3"})
    script = tmp_path / "s.txt"
    script.write_text("@host Hello.\n@guest Hi.\n")
    synth = ("synth", "--script", str(script), "--out-dir", str(tmp_path / "o"), "--no-align")
    for args, message in [(("--speaker", "Host=anna"), "lowercase letters"),
                          (("--speaker", "hots=anna"), "no `@name` line of the script has that speaker"),
                          (("--speaker", "host=anna"), "Fish takes no user recording"),
                          (("--voice", "Bob"), "lowercase letters")]:
        p = voiceover(*synth, *args, SKILLS_CONFIG=str(config))
        assert p.returncode == 1 and message in p.stderr, (args, p.stderr)
    script.write_text("@Host Hello.\n")
    p = voiceover(*synth, SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "lowercase letters" in p.stderr, p.stderr
    assert not (tmp_path / "o").exists()


def test_first_takes_per_speaker_written(tmp_path):
    """`Narrator.first_takes` gives the first take of the narrator and of each made-up speaker that `fish.takes` kept,
    and `write_takes` writes them as `voice.wav` and `voice-<name>.wav` with transcripts."""
    config = write_config(tmp_path / "config.yaml", providers={"f": FISH},
                          tasks={"speech": "f:drama-3"})
    code = f"""
from ai_models import fish
from ai_models.fish_take import Take
from voiceover_tool.cli import write_takes
from voiceover_tool.speech import Narrator
n = Narrator()
lines = n.lines(["Hi.", "@guest Hello.", "@host Hey.", "@guest Again."])
n.prepare(lines, "default")
fish.takes.keep("f:drama-3", None, Take(b"N", "Hi.", None))
fish.takes.keep("f:drama-3", "guest", Take(b"G", "Hello.", None))
fish.takes.keep("f:drama-3", "guest", Take(b"G2", "Again.", None))
fish.takes.keep("other:drama-3", "host", Take(b"H", "Hey.", None))
print(sorted(p.name for p in write_takes(__import__("pathlib").Path({str(tmp_path)!r}), n.first_takes())))
"""
    done = run_python(code, child_env(SKILLS_CONFIG=str(config)))
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["['voice-guest.wav',", "'voice.wav']"]
    assert "made-up voices" in done.stderr and "guest, host" in done.stderr
    assert (tmp_path / "voice-guest.wav").read_bytes() == b"G" and (tmp_path / "voice-guest.txt").read_text() == "Hello.\n"


def test_saved_fish_voice_seeds_and_new_name_saved(tmp_path):
    """With a fish model, `Narrator.prepare` seeds `fish.takes` with the saved take of a named Fish voice
    (`--voice anna`), so every request of the narrator has it as reference; a speaker mapped to a new name
    (`--speaker guest=nara`) has no seed, and `save_voices` saves its first take under that name; `voices` lists
    the model's voice and the saved Fish voices. Guards one Fish voice across commands (docs/voiceover.md)."""
    voices_dir = tmp_path / "voices"
    config = write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices_dir)},
                          providers={"f": FISH}, tasks={"speech": "f:drama-3"})
    code = f"""
import torch
from ai_models import fish
from ai_models.fish_take import Take
from voiceover_tool.speech import Narrator
Take(b"A", "[calm] Hi.", torch.zeros(10, 2, dtype=torch.long)).save({str(voices_dir / "anna.fish")!r})
n = Narrator(speakers={{"guest": "nara"}})
n.prepare(n.lines(["Hi.", "@guest Hello."]), "anna")
seeded = fish.takes.get("f:drama-3")
assert (seeded.wav, seeded.text) == (b"A", "[calm] Hi.") and seeded.codes.shape == (10, 2)
assert n.resolved == {{None: "default", "guest": "default"}}
assert fish.takes.get("f:drama-3", "guest") is None and n.save_voices() == []
fish.takes.keep("f:drama-3", "guest", Take(b"G", "Hello.", torch.ones(10, 3, dtype=torch.long)))
print([p.name for p in n.save_voices()], n.save_voices())
"""
    done = run_python(code, child_env(SKILLS_CONFIG=str(config)), timeout=25)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['nara.fish'] []"
    assert (voices_dir / "nara.fish" / "voice.wav").read_bytes() == b"G"
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 0 and p.stdout.split() == ["default", "(default)", "anna", "nara"], p.stderr


def test_one_fish_voice_name_is_one_voice(tmp_path):
    """Speakers given one new Fish voice name share one take key, the first speaker of that name (`--voice anna
    --speaker host=anna`: the narrator; `--speaker a=hero --speaker b=hero`: `a`), so `fish` gives them one voice;
    `first_takes` writes that take for each of them and `save_voices` saves it once under the name. Guards one name,
    one voice in every command (docs/voiceover.md, Fish voices across commands)."""
    voices_dir = tmp_path / "voices"
    config = write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices_dir)},
                          providers={"f": FISH}, tasks={"speech": "f:drama-3"})
    code = f"""
import torch
from ai_models import fish
from ai_models.fish_take import Take
from voiceover_tool.speech import Narrator
n = Narrator(speakers={{"host": "anna"}})
n.prepare(n.lines(["Hi.", "@host Hello.", "@guest Yo."]), "anna")
assert n.take_keys == {{None: None, "host": None, "guest": "guest"}}, n.take_keys
assert list(n.fish_voices) == [None]
n = Narrator(speakers={{"a": "hero", "b": "hero"}})
n.prepare(n.lines(["Hi.", "@a Hello.", "@b Hey."]), "default")
assert n.take_keys == {{None: None, "a": "a", "b": "a"}}, n.take_keys
fish.takes.keep("f:drama-3", "a", Take(b"H", "Hello.", torch.ones(10, 3, dtype=torch.long)))
takes = n.first_takes()
assert takes["a"] == takes["b"] == (b"H", "Hello.") and None not in takes, takes
print([p.name for p in n.save_voices()])
"""
    done = run_python(code, child_env(SKILLS_CONFIG=str(config)), timeout=25)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['hero.fish']"
    assert sorted(p.name for p in voices_dir.iterdir()) == ["hero.fish"]


def test_fish_voice_saved_by_another_command_meanwhile(tmp_path):
    """A new Fish voice name whose folder another command saves after `prepare` and before this command's first
    request of the voice seeds the voice then (`fish.takes.get`, which `fish` calls with the local-model lock held),
    and `save_voices` leaves it alone; a folder saved after this command made its own take is kept, and
    `save_voices` says on stderr that this command's voice differs. Guards two concurrent commands with one new
    name (docs/voiceover.md, Fish voices across commands)."""
    voices_dir = tmp_path / "voices"
    config = write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices_dir)},
                          providers={"f": FISH}, tasks={"speech": "f:drama-3"})
    code = f"""
import torch
from ai_models import fish
from ai_models.fish_take import Take
from voiceover_tool.speech import Narrator
codes = torch.zeros(10, 2, dtype=torch.long)
n = Narrator(speakers={{"guest": "nara", "host": "zed"}})
n.prepare(n.lines(["Hi.", "@guest Hello.", "@host Hey."]), "default")
Take(b"OTHER-N", "Hello.", codes).save({str(voices_dir / "nara.fish")!r})
seeded = fish.takes.get("f:drama-3", "guest")
assert seeded.wav == b"OTHER-N" and fish.takes.loaded("f:drama-3", "guest")
fish.takes.keep("f:drama-3", "host", Take(b"MINE-Z", "Hey.", codes))
Take(b"OTHER-Z", "Hey.", codes).save({str(voices_dir / "zed.fish")!r})
print(n.save_voices())
"""
    done = run_python(code, child_env(SKILLS_CONFIG=str(config)), timeout=25)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
    assert "Fish voice 'zed' was saved by another command" in done.stderr and "nara" not in done.stderr
    assert (voices_dir / "zed.fish" / "voice.wav").read_bytes() == b"OTHER-Z"
    assert (voices_dir / "nara.fish" / "voice.wav").read_bytes() == b"OTHER-N"


def test_params_parse_as_json_else_string():
    """`--param` values that parse as JSON are sent as that value, others as strings."""
    from voiceover_tool.cli import _params

    assert _params(["seed=7", 'extra_params={"temperature": 0.8}', "language=English"]) == {
        "seed": 7, "extra_params": {"temperature": 0.8}, "language": "English"}


def test_earlier_model_settings_refused(tmp_path):
    """A `VOICEOVER_*` setting of the earlier layout stops every command with one message naming its new place
    (`plugin_settings.old_keys`): VOICEOVER_VOICES_DIR moved to `voiceover.voices_dir`, the model settings are
    `tasks.speech`, `tasks.align` and their providers, VOICEOVER_MODEL_DIR becomes the providers' `dir`."""
    config = tmp_path / "config.yaml"
    config.write_text("settings:\n  VOICEOVER_KOKORO_VOICE: af_heart\n  VOICEOVER_MODEL_DIR: /old/voiceover\n"
                      "  VOICEOVER_VOICES_DIR: /old/voiceover/voices\n", encoding="utf-8")
    p = voiceover("voices", SKILLS_CONFIG=str(config))
    assert p.returncode == 1 and "Traceback" not in p.stderr, p.stderr
    for part in ("settings.VOICEOVER_KOKORO_VOICE: no longer read", "tasks.speech and tasks.align",
                 "dir: /old/voiceover", "settings.VOICEOVER_VOICES_DIR: moved to voiceover.voices_dir"):
        assert part in p.stderr, (part, p.stderr)
    config = write_config(tmp_path / "ok.yaml", voiceover={"voices_dir": str(tmp_path)}, providers={"oai": OAI},
                          tasks={"speech": "oai:tts-1"})
    assert voiceover("voices", SKILLS_CONFIG=str(config)).returncode == 0
