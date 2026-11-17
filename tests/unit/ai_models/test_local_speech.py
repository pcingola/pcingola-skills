"""`ai_models.speech` for the local speech kinds and what each kind takes (docs/ai_models.md, Local speech and
alignment): defaults, checks, voice listing and configuration errors, without loading a model."""

import pytest

from ai_models import AIModelsError, ConfigError, align, chatterbox, kokoro, speech
from plugin_settings import SPEECH_KINDS
from plugin_settings import KokoroModel

KOKORO_MODEL = {"model_url": "http://127.0.0.1:1/m.onnx", "voices_url": "http://127.0.0.1:1/v.bin",
                "langs": {"af_": "en-us", "bm_": "en-gb"}}
KOKORO = {"kind": "kokoro", "models": {"kokoro-v1.0": KOKORO_MODEL}}
CHATTERBOX_MODEL = {"url": "http://127.0.0.1:1", "files": ["a.pt"]}
CHATTERBOX = {"kind": "chatterbox", "models": {"chatterbox-turbo": CHATTERBOX_MODEL}}
FISH_MODEL = {"repo": "org/tts"}
FISH = {"kind": "fish", "models": {"drama-3": FISH_MODEL}}


def test_default_voices_and_checks(write_config):
    """A model entry's `voice` replaces its kind's default voice and its `voices` are the list, for a local and a
    remote model; `check` refuses a speed outside the kind's range or with a kind without speed, and instructions
    with a kind that takes none; a fish model takes instructions only with `style` and has one voice; a model of a
    kind without speech models is refused (`TASK_KINDS`)."""
    george = {"voice": "bm_george", "voices": ["bm_george"]}
    write_config({"providers": {"k": KOKORO, "k2": {"kind": "kokoro", "models": {
                                    "kokoro-v1.0": {**KOKORO_MODEL, **george}}},
                                "o": {"kind": "openai", "base_url": "http://127.0.0.1:9/v1",
                                      "models": {"tts2": {"voice": "ash"}}},
                                "g": {"kind": "google", "api_key": "k"},
                                "f": FISH, "fs": {**FISH, "models": {"drama-3": {**FISH_MODEL,
                                                                                 "style": "[{instructions}] {text}"}}},
                                "cb": CHATTERBOX, "local": {"kind": "diffusers", "models": {"flux": {"repo": "r"}}}},
                  "tasks": {"speech": "k:kokoro-v1.0"}})
    assert speech.model_of().default_voice == "af_heart"
    assert speech.model_of("k2:kokoro-v1.0").default_voice == "bm_george"
    assert speech.voices("k2:kokoro-v1.0") == ["bm_george"]
    assert speech.voices("o:tts") == ["marin"] and speech.voices("g:tts") == ["Kore"]
    assert speech.voices("o:tts2") == ["ash"]
    assert speech.voices("cb:chatterbox-turbo") == ["default"]
    assert speech.voices("f:drama-3") == ["default"] and speech.model_of("f:drama-3").traits.one_voice
    assert speech.check(speed=1.5).id == "k:kokoro-v1.0"
    assert speech.check("o:tts", speed=3.0, instructions="calm").kind == "openai"
    for model, kw, message in [("k:kokoro-v1.0", {"speed": 3.0}, "between 0.5 and 2"),
                               ("k:kokoro-v1.0", {"instructions": "calm"}, "takes no instructions"),
                               ("g:tts", {"speed": 1.2}, "ask for the pace in the instructions"),
                               ("cb:chatterbox-turbo", {"speed": 1.2}, "no speed setting"),
                               ("cb:chatterbox-turbo", {"instructions": "calm"}, "takes no instructions"),
                               ("f:drama-3", {"instructions": "whisper"}, "takes no instructions"),
                               ("fs:drama-3", {"speed": 1.2}, "ask for the pace in the instructions"),
                               ("fs:drama-3", {"params": {"seed": 7}}, "takes no request parameters")]:
        with pytest.raises(AIModelsError, match=message):
            speech.check(model, **kw)
    assert speech.check("fs:drama-3", instructions="whisper").instructions
    assert speech.model_of("cb:chatterbox-turbo").traits.clones and not speech.model_of().traits.clones
    with pytest.raises(ConfigError, match="task speech takes kinds"):
        speech.model_of("local:flux")


def test_kokoro_language_of_a_voice():
    """A Kokoro voice's espeak language comes from the prefixes of `langs`; a voice of no listed prefix is
    refused."""
    entry = KokoroModel(**KOKORO_MODEL)
    assert [kokoro.lang(entry, "k:m", v) for v in ("af_heart", "bm_george")] == ["en-us", "en-gb"]
    with pytest.raises(AIModelsError, match="no language"):
        kokoro.lang(entry, "k:m", "ff_siwis")


def test_chatterbox_voice_and_reference_checks(tmp_path):
    """A Chatterbox voice is `default` (None, the built-in voice) or a recording file, else refused; a reference
    recording of 5 s or less and a file that is not a recording are refused before the model sees them."""
    with pytest.raises(AIModelsError, match="neither 'default' nor a reference recording"):
        chatterbox.reference("bob")
    assert chatterbox.reference("default") is None
    short = tmp_path / "short.wav"
    short.write_bytes(speech.wav(bytes(2 * 2 * 24_000), 24_000))
    assert chatterbox.reference(str(short)) == str(short.resolve())
    with pytest.raises(AIModelsError, match="2.0 s; a reference must be longer than 5 s"):
        chatterbox.check_reference(str(short))
    text = tmp_path / "notes.txt"
    text.write_text("not audio", encoding="utf-8")
    with pytest.raises(AIModelsError, match="not a readable recording"):
        chatterbox.check_reference(str(text))


def test_align_model_of_another_kind_refused(write_config):
    """The align task takes only a `torchaudio` model with an entry; without `tasks.align`, its provider or the
    entry, the error names the task, provider or key."""
    write_config({"providers": {"o": {"kind": "openai", "base_url": "http://127.0.0.1:9/v1"},
                                "t": {"kind": "torchaudio"}}, "tasks": {}})
    with pytest.raises(ConfigError, match="no model for task 'align'"):
        align.aligner()
    with pytest.raises(ConfigError, match="provider 'torchaudio' is not in providers"):
        align.aligner("torchaudio:MMS_FA")
    with pytest.raises(ConfigError, match="model 'MMS_FA' is not in providers.t.models"):
        align.aligner("t:MMS_FA")
    with pytest.raises(ConfigError, match="task align takes kinds torchaudio"):
        align.aligner("o:mms")


def test_model_of_kind(write_config, tmp_path):
    """`model_of_kind` gives `tasks.speech` when its provider has the kind, else the first routes row of a provider
    of the kind, else None."""
    write_config({"providers": {"k": KOKORO, "cb": CHATTERBOX, "o": {"kind": "openai", "api_key": "k"}},
                  "tasks": {"speech": "o:tts"}})
    (tmp_path / "routes.md").write_text("| task | model | when | why |\n|---|---|---|---|\n"
                                        "| speech | cb:chatterbox-turbo | only when cloned | x |\n", encoding="utf-8")
    assert speech.model_of_kind("openai") == "o:tts"
    assert speech.model_of_kind("chatterbox") == "cb:chatterbox-turbo"
    assert speech.model_of_kind("kokoro") is None


def test_weights_dir_from_the_caller(write_config):
    """A local model's weights directory is the provider's `dir`, else the caller's `weights_dir`; with neither,
    the error asks for `dir`."""
    write_config({"providers": {"k": KOKORO, "kd": {**KOKORO, "dir": "/own"}}, "tasks": {}})
    assert str(speech.model_of("k:kokoro-v1.0", "/caller").spec.dir) == "/caller"
    assert str(speech.model_of("kd:kokoro-v1.0", "/caller").spec.dir) == "/own"
    with pytest.raises(ConfigError, match="set `dir`"):
        m = speech.model_of("k:kokoro-v1.0")
        kokoro.files(m.spec, m.entry, "kokoro-v1.0")


def test_traits_cover_the_speech_kinds():
    """`speech.TRAITS` has an entry for each kind of `SPEECH_KINDS`, the kinds task speech takes, and no other.
    Guards the kind grouping of the schema and the traits table going apart."""
    assert set(speech.TRAITS) == set(SPEECH_KINDS)
