"""`ai_models.omni`: the parts of the vLLM-Omni speech kind that run without a server (docs/ai_models.md, Speech
models of vLLM-Omni)."""

import asyncio
import base64
import io
import os
import wave
from pathlib import Path

import pytest
import yaml

from ai_models import AIModelsError, ConfigError, omni

SPEC = {"kind": "vllm-omni", "python": "/env/bin/python", "repo": "org/tts", "deploy": "tts.yaml",
        "memory": 70, "style": "[{instructions}] {text}"}


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


def test_memory_bytes_and_device_share():
    """`memory` is GB of the stages together; a missing, non-numeric or non-positive one, or one above the device,
    is a ConfigError."""
    assert omni.memory_bytes(SPEC, "fish") == 70 * 10**9
    assert omni.device_share(70 * 10**9, 140 * 10**9, "fish") == pytest.approx(0.5)
    with pytest.raises(ConfigError, match="needs `memory`"):
        omni.memory_bytes({"kind": "vllm-omni"}, "fish")
    for bad in (0, -1, "lots"):
        with pytest.raises(ConfigError, match="memory must be"):
            omni.memory_bytes({**SPEC, "memory": bad}, "fish")
    with pytest.raises(ConfigError, match="exceeds the device"):
        omni.device_share(150 * 10**9, 140 * 10**9, "fish")


def test_memory_share_names_its_replacement():
    """A config written for the former `memory_share` gets an error that names `memory` and the Drama 3 value."""
    old = {k: v for k, v in SPEC.items() if k != "memory"} | {"memory_share": 0.6}
    with pytest.raises(ConfigError, match=r"`memory_share` was replaced by `memory`.*Drama 3: 70"):
        omni.memory_bytes(old, "fish")


def test_overhead_defaults_to_the_measured_value():
    """Without `overhead` the server's memory outside `memory` is `OVERHEAD_GB`; the provider's key replaces it."""
    assert omni.overhead_bytes(SPEC, "fish") == int(omni.OVERHEAD_GB * 10**9)
    assert omni.overhead_bytes({**SPEC, "overhead": 3}, "fish") == 3 * 10**9
    with pytest.raises(ConfigError, match="overhead must be"):
        omni.overhead_bytes({**SPEC, "overhead": 0}, "fish")


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
        asyncio.run(omni.aspeak("fish", SPEC, "tts", "Hi.", "default", None, 1.5))


def test_server_env_adds_the_provider_env():
    """The provider's `env` values reach the server's environment as strings, over this process's environment."""
    env = omni.server_env({"env": {"VLLM_USE_FLASHINFER_SAMPLER": 0}})
    assert env["VLLM_USE_FLASHINFER_SAMPLER"] == "0" and "PATH" in env


def test_server_env_on_an_integrated_gpu_turns_the_graph_estimate_off_unless_the_provider_sets_it():
    """On an integrated GPU the CUDA graph memory estimate is off by default (`INTEGRATED_ENV`); the provider's
    `env` overrides it; on a discrete GPU it is left to vLLM."""
    key = "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS"
    assert omni.server_env({}, shared=True)[key] == "0"
    assert omni.server_env({"env": {key: 1}}, shared=True)[key] == "1"
    assert omni.server_env({}, shared=False).get(key) == os.environ.get(key)


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


# Log lines of real Drama 3 starts on the GB10 that failed for memory, and one of a start that came up.
KV_FAILURE = ("ValueError: No available memory for the cache blocks. Try increasing `gpu_memory_utilization` when "
              "initializing the engine.")
OOM_FAILURE = "torch.AcceleratorError: CUDA error: out of memory"
STARTED = "(APIServer pid=1) INFO 11-15 08:53:13 [launcher.py:47] Application startup complete."


def test_start_failure_kinds_and_advice():
    """No KV cache memory is `KV_CACHE`, whose advice raises `memory`; a CUDA out-of-memory error is
    `OUT_OF_MEMORY`, whose advice frees memory or lowers `memory`; a started server is neither."""
    assert omni.start_failure(f"...\n{KV_FAILURE}\n...") is omni.StartFailure.KV_CACHE
    assert omni.start_failure(OOM_FAILURE) is omni.StartFailure.OUT_OF_MEMORY
    assert omni.start_failure(STARTED) is None
    assert "raise `memory`" in omni.failure_advice(omni.StartFailure.KV_CACHE, "fish")
    advice = omni.failure_advice(omni.StartFailure.OUT_OF_MEMORY, "fish")
    assert "lower `memory`" in advice and "raise" not in advice


def test_start_failure_reads_the_whole_log(tmp_path):
    """A failure line followed by more than `LOG_TAIL` characters of shutdown output is still found: the log is
    classified whole, while `tail` quotes only its end."""
    log = tmp_path / "server.log"
    log.write_text(f"{KV_FAILURE}\n" + "shutting down a stage worker\n" * (omni.LOG_TAIL // 10))
    assert KV_FAILURE not in omni.tail(log)
    assert omni.start_failure(omni.read_log(log)) is omni.StartFailure.KV_CACHE


def test_context_out_of_memory_becomes_a_memory_error():
    """A CUDA out-of-memory error of this process's first CUDA calls becomes the memory error that names the model;
    another runtime error passes unchanged."""
    with pytest.raises(AIModelsError, match="org/tts: CUDA ran out of memory as this process started"):
        with omni.context_out_of_memory("org/tts"):
            raise RuntimeError("CUDA error: out of memory")
    with pytest.raises(RuntimeError, match="device-side assert"):
        with omni.context_out_of_memory("org/tts"):
            raise RuntimeError("CUDA error: device-side assert triggered")


def test_params_merge_and_built_fields_refused():
    """`request_body` adds the caller's request fields and refuses one it builds itself (`BUILT_FIELDS`)."""
    body = omni.request_body("tts", "Hi.", "default", None, {"seed": 7, "extra_params": {"temperature": 0.8}})
    assert body == {"model": "tts", "input": "Hi.", "response_format": "wav", "seed": 7,
                    "extra_params": {"temperature": 0.8}}
    for key in ("input", "ref_audio", "model"):
        with pytest.raises(AIModelsError, match=key):
            omni.request_body("tts", "Hi.", "default", None, {key: "x"})


def test_first_take_kept_per_speaker():
    """`keep_take` keeps the first `default` answer of each speaker (None: the narrator) and none for a reference
    voice; `first_take` returns it, and a later answer does not replace it."""
    omni.keep_take("p1", None, "default", b"a", "one")
    omni.keep_take("p1", "guest", "default", b"b", "two")
    omni.keep_take("p1", "guest", "default", b"c", "three")
    omni.keep_take("p1", "host", "/ref.wav", b"d", "four")
    assert omni.first_take("p1") == (b"a", "one") and omni.first_take("p1", "guest") == (b"b", "two")
    assert omni.first_take("p1", "host") is None and omni.first_take("p2") is None
    body = omni.request_body("tts", "Hi.", "default", omni.first_take("p1", "guest"))
    assert body["ref_text"] == "two" and body["ref_audio"].startswith("data:audio/wav;base64,")
