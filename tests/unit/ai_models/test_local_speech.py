"""`ai_models.speech` for the local speech kinds and what each kind takes (docs/ai_models.md, Local speech and
alignment): defaults, checks, voice listing and configuration errors, without loading a model."""

import subprocess
import sys

import pytest

from ai_models import AIModelsError, ConfigError, align, chatterbox, kokoro, speech
from plugin_settings import ChatterboxProvider, KokoroProvider

KOKORO = {"kind": "kokoro", "model_url": "http://127.0.0.1:1/m.onnx", "voices_url": "http://127.0.0.1:1/v.bin",
          "langs": {"af_": "en-us", "bm_": "en-gb"}}


CHATTERBOX = {"kind": "chatterbox", "python": "/nonexistent/python", "url": "http://127.0.0.1:1", "files": ["a.pt"]}
OMNI = {"kind": "vllm-omni", "python": "/nonexistent/python", "repo": "org/tts", "deploy": "tts.yaml", "memory": 70}


def chatterbox_spec(tmp_path, python: str, **kw) -> ChatterboxProvider:
    """A chatterbox provider whose model files exist, so the worker starts without a download."""
    d = tmp_path / "w" / "chatterbox-turbo"
    d.mkdir(parents=True)
    (d / "a.pt").write_bytes(b"x")
    return ChatterboxProvider(**{**CHATTERBOX, "python": python, "dir": str(tmp_path / "w"), **kw})


def test_default_voices_and_checks(write_config):
    """A provider's `voice` replaces its kind's default voice and its `voices` are the list; `check` refuses a
    speed outside the kind's range or with a kind without speed, and instructions with a kind that takes none; a
    vllm-omni provider takes instructions only with `style`."""
    write_config({"providers": {"k": KOKORO, "k2": {**KOKORO, "voice": "bm_george", "voices": ["bm_george"]},
                                "o": {"kind": "openai", "base_url": "http://127.0.0.1:9/v1"},
                                "g": {"kind": "google", "api_key": "k"},
                                "f": OMNI, "fs": {**OMNI, "style": "[{instructions}] {text}"},
                                "cb": CHATTERBOX, "local": {"kind": "diffusers"}},
                  "tasks": {"speech": "k:kokoro-v1.0"}})
    assert speech.model_of().default_voice == "af_heart"
    assert speech.model_of("k2:kokoro-v1.0").default_voice == "bm_george"
    assert speech.voices("k2:kokoro-v1.0") == ["bm_george"]
    assert speech.voices("o:tts") == ["marin"] and speech.voices("g:tts") == ["Kore"]
    assert speech.voices("cb:chatterbox-turbo") == ["default"]
    assert speech.check(speed=1.5).id == "k:kokoro-v1.0"
    assert speech.check("o:tts", speed=3.0, instructions="calm").kind == "openai"
    for model, kw, message in [("k:kokoro-v1.0", {"speed": 3.0}, "between 0.5 and 2"),
                               ("k:kokoro-v1.0", {"instructions": "calm"}, "takes no instructions"),
                               ("g:tts", {"speed": 1.2}, "ask for the pace in the instructions"),
                               ("cb:chatterbox-turbo", {"speed": 1.2}, "no speed setting"),
                               ("cb:chatterbox-turbo", {"instructions": "calm"}, "takes no instructions"),
                               ("f:drama-3", {"instructions": "whisper"}, "takes no instructions")]:
        with pytest.raises(AIModelsError, match=message):
            speech.check(model, **kw)
    assert speech.check("fs:drama-3", instructions="whisper").instructions
    assert speech.model_of("cb:chatterbox-turbo").traits.clones and not speech.model_of().traits.clones
    with pytest.raises(ConfigError, match="has no speech models"):
        speech.model_of("local:flux")


def test_kokoro_language_of_a_voice():
    """A Kokoro voice's espeak language comes from the prefixes of `langs`; a voice of no listed prefix is
    refused."""
    spec = KokoroProvider(**KOKORO)
    assert [kokoro.lang(spec, "k", v) for v in ("af_heart", "bm_george")] == ["en-us", "en-gb"]
    with pytest.raises(AIModelsError, match="no language"):
        kokoro.lang(spec, "k", "ff_siwis")


def test_chatterbox_worker_errors(tmp_path):
    """An interpreter that cannot run is a `ConfigError` naming the provider; a worker that exits before its ready
    line is an `AIModelsError` with its exit code; a voice that is neither `default` nor a file is refused."""
    with pytest.raises(ConfigError, match="cannot run"):
        chatterbox.worker(chatterbox_spec(tmp_path / "a", str(tmp_path / "no-python")), "cb", "chatterbox-turbo")
    with pytest.raises(AIModelsError, match="exited with code 1"):
        chatterbox.worker(chatterbox_spec(tmp_path / "b", "/bin/false"), "cb2", "chatterbox-turbo")
    with pytest.raises(AIModelsError, match="neither 'default' nor a reference recording"):
        chatterbox.reference("bob")
    assert chatterbox.reference("default") is None


def test_chatterbox_load_timeout_and_log_cleanup(tmp_path):
    """A worker that gives no ready line within `start_timeout` is stopped with an error naming the limit; a worker
    that exits with code 0 when stopped takes its log directory with it."""
    spec = chatterbox_spec(tmp_path, sys.executable, start_timeout=0.01)
    with pytest.raises(AIModelsError, match="no answer in 0 s"):
        chatterbox.worker(spec, "cb3", "chatterbox-turbo")
    log = tmp_path / "logdir" / "worker.log"
    log.parent.mkdir()
    log.write_text("")
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    chatterbox.Worker(proc, log).stop()
    assert proc.returncode == 0 and not log.parent.exists()


def test_align_model_of_another_kind_refused(write_config):
    """The align task takes only a `torchaudio` provider; without `tasks.align`, or without its provider, the error
    names the task or provider."""
    write_config({"providers": {"o": {"kind": "openai", "base_url": "http://127.0.0.1:9/v1"}}, "tasks": {}})
    with pytest.raises(ConfigError, match="no model for task 'align'"):
        align.aligner()
    with pytest.raises(ConfigError, match="no provider 'torchaudio'"):
        align.aligner("torchaudio:MMS_FA")
    with pytest.raises(ConfigError, match="has no align models"):
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
        kokoro.files(speech.model_of("k:kokoro-v1.0").spec, "kokoro-v1.0")
