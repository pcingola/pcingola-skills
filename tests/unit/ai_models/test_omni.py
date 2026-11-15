"""`ai_models.omni`: the parts of the vLLM-Omni speech kind that run without a server (docs/ai_models.md, Speech
models of vLLM-Omni)."""

import base64
import io
import wave
from pathlib import Path

import pytest
import torch
import yaml

from ai_models import AIModelsError, ConfigError, local, omni
from tests.prereq import requires

SPEC = {"kind": "vllm-omni", "python": "/env/bin/python", "repo": "org/tts", "deploy": "tts.yaml",
        "memory_share": 0.8, "style": "[{instructions}] {text}"}


def test_overlay_scales_stage_fractions_and_turns_mps_off(tmp_path):
    """Stages of 0.78 and 0.1 keep their proportions and together take the given share; MPS is off."""
    base = tmp_path / "base.yaml"
    base.write_text(yaml.safe_dump({"stages": [{"stage_id": 0, "gpu_memory_utilization": 0.78},
                                               {"stage_id": 1, "gpu_memory_utilization": 0.1}],
                                    "platforms": {"cuda": {"cuda_mps": True}}}))
    out = omni.overlay(base, 0.44)
    assert out["base_config"] == str(base)
    assert out["platforms"] == {"cuda": {"cuda_mps": False}}
    fractions = {s["stage_id"]: s["gpu_memory_utilization"] for s in out["stages"]}
    assert fractions == {0: pytest.approx(0.39, abs=1e-4), 1: pytest.approx(0.05, abs=1e-4)}


def test_overlay_without_fractions_is_a_config_error(tmp_path):
    """A deploy config with no stage fraction cannot be scaled: ConfigError."""
    base = tmp_path / "base.yaml"
    base.write_text(yaml.safe_dump({"stages": [{"stage_id": 0}]}))
    with pytest.raises(ConfigError, match="gpu_memory_utilization"):
        omni.overlay(base, 0.5)


def test_memory_share_of_free_over_total():
    """The share is memory_share of the free bytes over the total; a missing or out-of-range key is a ConfigError."""
    assert omni.memory_share(SPEC, "fish", free=100, total=200) == pytest.approx(0.4)
    with pytest.raises(ConfigError, match="memory_share"):
        omni.memory_share({**SPEC, "memory_share": 1.5}, "fish", free=100, total=200)
    with pytest.raises(ConfigError, match="needs `memory_share`"):
        omni.memory_share({"kind": "vllm-omni"}, "fish", free=100, total=200)


def test_deploy_path_takes_an_existing_file(tmp_path):
    """A `deploy` that names a file is used as it is, without asking the server environment."""
    f = tmp_path / "d.yaml"
    f.write_text("stages: []\n")
    assert omni.deploy_path("/no/python", str(f)) == f


def test_command_serves_the_repo_on_loopback(tmp_path):
    """The server command runs `vllm serve <repo> --omni` on 127.0.0.1 with the model id as served name."""
    cmd = omni.command("/env/bin/python", "org/tts", tmp_path / "d.yaml", 8123, "tts")
    assert cmd[:6] == ["/env/bin/python", "-m", "vllm.entrypoints.cli.main", "serve", "org/tts", "--omni"]
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1" and cmd[cmd.index("--port") + 1] == "8123"
    assert cmd[cmd.index("--served-model-name") + 1] == "tts"
    assert omni.command("/p", "r", tmp_path, 1, "m", ["--stage-init-timeout", 900])[-2:] == ["--stage-init-timeout", "900"]


def test_styled_puts_instructions_into_the_text():
    """`style` formats the instructions into the text; no instructions leave it alone; no `style` refuses them."""
    assert omni.styled(SPEC, "fish", "Hello.", "whisper") == "[whisper] Hello."
    assert omni.styled(SPEC, "fish", "Hello.", None) == "Hello."
    with pytest.raises(AIModelsError, match="no `style`"):
        omni.styled({"kind": "vllm-omni"}, "fish", "Hello.", "whisper")


def _wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 1600)


def test_request_body_default_voice_has_no_reference():
    """The `default` voice sends no reference and asks for WAV."""
    assert omni.request_body("tts", "Hi.", "default") == {"model": "tts", "input": "Hi.", "response_format": "wav"}


def test_request_body_with_reference_recording(tmp_path):
    """A reference recording goes as a data: URI of its bytes, with the transcript of its .txt file."""
    ref = tmp_path / "alice.wav"
    _wav(ref)
    ref.with_suffix(".txt").write_text("This is Alice.\n")
    body = omni.request_body("tts", "Hi.", str(ref))
    assert body["ref_text"] == "This is Alice."
    head, data = body["ref_audio"].split(",", 1)
    assert head == "data:audio/x-wav;base64" or head == "data:audio/wav;base64"
    with wave.open(io.BytesIO(base64.b64decode(data))) as w:
        assert w.getnframes() == 1600


def test_request_body_default_voice_uses_the_first_take(tmp_path):
    """Guards one speaker per command: with `default` and a first take, the take goes as `ref_audio` (a WAV data:
    URI of its bytes) with its text; a reference recording takes precedence over the take."""
    take_wav = tmp_path / "take.wav"
    _wav(take_wav)
    take = (take_wav.read_bytes(), "The harbour wakes.")
    body = omni.request_body("tts", "Hi.", "default", take)
    assert body["ref_text"] == "The harbour wakes."
    assert base64.b64decode(body["ref_audio"].split(",", 1)[1]) == take[0]
    ref = tmp_path / "alice.wav"
    _wav(ref)
    ref.with_suffix(".txt").write_text("This is Alice.\n")
    assert omni.request_body("tts", "Hi.", str(ref), take)["ref_text"] == "This is Alice."
    assert omni.first_take("no-such-provider") is None


def test_reference_needs_a_file_and_a_transcript(tmp_path):
    """A voice that is not `default` must be an existing file with a .txt transcript."""
    with pytest.raises(AIModelsError, match="neither"):
        omni.reference("marin")
    ref = tmp_path / "bob.wav"
    _wav(ref)
    with pytest.raises(AIModelsError, match="no transcript"):
        omni.reference(str(ref))


def test_speed_is_refused_before_any_server_starts():
    """A speed other than 1 fails before a server starts (the kind has no speed)."""
    with pytest.raises(AIModelsError, match="no speed"):
        omni.speak("fish", SPEC, "tts", "Hi.", "default", None, 1.5)


def test_server_env_adds_the_provider_env():
    """The provider's `env` values reach the server's environment as strings, over this process's environment."""
    env = omni.server_env({"env": {"VLLM_USE_FLASHINFER_SAMPLER": 0}})
    assert env["VLLM_USE_FLASHINFER_SAMPLER"] == "0" and "PATH" in env


def test_stop_kills_a_group_member_that_outlives_the_main_process():
    """`Server.stop` waits for the whole process group, not only the main process: a worker that ignores SIGTERM
    is killed with SIGKILL after the wait, and no process of the group is left. Guards stage workers keeping the
    memory after the server's main process exited."""
    import subprocess
    import time

    proc = subprocess.Popen(["sh", "-c", "(trap '' TERM; while :; do sleep 0.1; done) & exec sleep 60"],
                            start_new_session=True)
    time.sleep(0.3)
    srv = omni.Server(proc, "http://127.0.0.1:1", Path("/dev/null"), "m")
    started = time.monotonic()
    srv.stop(1.0)
    assert not omni.group_alive(proc.pid)
    assert time.monotonic() - started < 10
    srv.stop(1.0)  # a second stop of a gone group returns


def test_sigterm_runs_atexit():
    """After `exit_on_sigterm`, a SIGTERM raises SystemExit, so atexit handlers (the server stop) run and the exit
    code is 128 + 15. Guards a SIGTERM that kills the caller without stopping the server's group."""
    import subprocess
    import sys

    code = ("import atexit, os, signal, time; from ai_models import omni; omni.exit_on_sigterm(); "
            "atexit.register(lambda: print('stopped', flush=True)); os.kill(os.getpid(), signal.SIGTERM); "
            "time.sleep(5)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 143
    assert r.stdout.strip() == "stopped"


@requires(torch.cuda.is_available(), "a CUDA device")
def test_vllm_free_memory_is_positive_and_within_cuda_free():
    """The vLLM sizing figure from `local.free_memory` is positive and at most `torch.cuda.mem_get_info`'s free bytes
    on an integrated GPU (on a discrete one it is `local.free_memory` itself)."""
    free = local.free_memory("cuda")
    got = omni.vllm_free_memory(free, "cuda")
    assert got > 0
    assert got <= free
    if local.integrated("cuda"):
        assert got <= torch.cuda.mem_get_info()[0]
