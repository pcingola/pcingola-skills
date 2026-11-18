"""Memory safety of local models without a GPU: the weight sum, the memory check and the process lock
(docs/ai_models.md, Local models). Each case that takes the lock runs in a child process, because the lock lasts for
the life of the process. The cases that need a GPU are in tests/integration/ai_models/test_memory.py."""

import gc
import time
import weakref

import pytest
import torch

from ai_models import AIModelsError, local
from tests.local_lock import HOLDER, lock_env, start
from tests.settings_env import write_config


def test_weight_bytes_sums_parameters_and_buffers():
    """Guards the memory check: every parameter and buffer of each torch module counts, at its element size, and
    a component that is no module counts 0."""
    lin = torch.nn.Linear(4, 3).to(torch.bfloat16)  # 12 weights + 3 biases, 2 bytes each
    norm = torch.nn.BatchNorm1d(5)  # 2 * 5 parameters, 3 buffers (5 + 5 floats, 1 int64), float32
    assert local.weight_bytes([lin, norm, None, "tokenizer"]) == 15 * 2 + 10 * 4 + 10 * 4 + 8


def test_weights_over_free_memory_raise():
    """A pipeline whose weights exceed the free memory is refused with both sizes before any weight moves."""
    with pytest.raises(AIModelsError, match=r"some/model: its weights need 3\.0 GB and the device has 2\.0 GB free"):
        local.check_memory("some/model", 3 * 10**9, 2 * 10**9)
    local.check_memory("some/model", 2 * 10**9, 3 * 10**9)


def test_second_process_waits_for_the_lock(tmp_path):
    """Guards one local model process at a time: a second process blocks on the lock until the first exits, and
    its stderr names the holder's PID."""
    env = lock_env(tmp_path)
    first = start(HOLDER, env)
    try:
        assert first.stdout.readline().strip() == "held", first.stderr.read()
        second = start(HOLDER, env)
        try:
            time.sleep(3)
            assert second.poll() is None
            first.stdin.close()
            first.wait(timeout=10)
            out, err = second.communicate("\n", timeout=10)
            assert out.strip() == "held", err
            assert f"waiting for process {first.pid}," in err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait(timeout=5)
    assert (tmp_path / local.LOCK_FILE).exists()


SLOW_EXIT = """
    import sys, time
    from ai_models import local
    local.hold_lock()
    print("held", flush=True)
    sys.stdin.readline()
    local.release_lock()  # the lock goes before the process does, as when the OS tears a process down
    time.sleep(2)
"""


WAITER = """
    import psutil
    from ai_models import local
    holder = int(open(local.Path(local.tempfile.gettempdir()) / local.PID_FILE).read())
    waited = local.hold_lock()
    print(waited, psutil.pid_exists(holder), flush=True)
"""


def test_waiter_returns_after_the_holder_exits(tmp_path):
    """Guards the refused LTX renders: a process that waited for the lock goes on only after the previous holder
    has exited, not when the lock file is released, so the holder's memory is not counted as used."""
    env = lock_env(tmp_path)
    first = start(SLOW_EXIT, env)
    try:
        assert first.stdout.readline().strip() == "held", first.stderr.read()
        second = start(WAITER, env)
        try:
            time.sleep(2)
            first.stdin.write("\n")
            first.stdin.flush()
            first.wait(timeout=10)  # reaped as it exits, as a shell reaps a finished command
            out, err = second.communicate(timeout=15)
            assert out.split() == ["True", "False"], err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait(timeout=5)


UNLOADER = """
    import sys
    from ai_models import local
    cache = {"model": object()}
    local.on_unload(cache)
    local.hold_lock()
    local.unload()
    print("unloaded", len(cache), flush=True)
    sys.stdin.readline()
"""


def test_unload_releases_the_lock_at_once(tmp_path):
    """Guards integration tests that load a local model in the test process (tests/integration/conftest.py):
    after `unload`, the registered caches are empty and another process takes the lock without waiting, while
    the first process still runs."""
    env = lock_env(tmp_path)
    first = start(UNLOADER, env)
    try:
        assert first.stdout.readline().split() == ["unloaded", "0"], first.stderr.read()
        started = time.monotonic()
        out, err = start(HOLDER, env).communicate("\n", timeout=20)
        assert out.strip() == "held", err
        assert "waiting" not in err
        assert time.monotonic() - started < 10
    finally:
        first.kill()
        first.wait(timeout=5)


class Cycle:
    """An object in a reference cycle: only a garbage collection frees it once unreferenced."""

    def __init__(self):
        self.me = self


def unload_frees_cycle(cache: dict) -> bool:
    """Whether `local.unload` freed an unreferenced `Cycle`, with automatic collection off, with `cache` registered."""
    local.on_unload(cache)
    cycle = Cycle()
    ref = weakref.ref(cycle)
    del cycle
    enabled = gc.isenabled()
    gc.disable()
    try:
        local.unload()
        return ref() is None
    finally:
        if enabled:
            gc.enable()


def test_unload_collects_only_when_something_was_held():
    """Guards fast teardowns of tests that load no model: `unload` collects garbage (and empties the CUDA
    allocator cache) when a registered cache held an entry, and skips both when nothing was held. This process
    never holds the lock (the lock cases run in child processes)."""
    assert not unload_frees_cycle({})
    held = {"model": object()}
    assert unload_frees_cycle(held)
    assert held == {}


IMPATIENT = """
    from ai_models import AIModelsError, local
    try:
        local.hold_lock()
    except AIModelsError as e:
        print(e, flush=True)
"""


def test_lock_wait_limits_the_wait(tmp_path):
    """Guards against a test or command that waits forever for the local models: with `local_models.lock_wait: 1`,
    a process fails within a few seconds while another holds the lock, with an error that names the holder's PID,
    the lock file and the setting."""
    env = lock_env(tmp_path)
    impatient = {**env, "SKILLS_CONFIG": str(write_config(tmp_path / "wait.yaml", local_models={"lock_wait": 1}))}
    first = start(HOLDER, env)
    try:
        assert first.stdout.readline().strip() == "held", first.stderr.read()
        started = time.monotonic()
        out, err = start(IMPATIENT, impatient).communicate(timeout=20)
        assert time.monotonic() - started < 10, err
        assert f"process {first.pid} holds local models (lock {tmp_path / local.LOCK_FILE})" in out, err
        assert "within 1 s (local_models.lock_wait)" in out
    finally:
        first.kill()
        first.wait(timeout=5)


def test_holder_text_has_size_and_release():
    """`str(local.Holder)` is the holder's name, its size in GB to one decimal and, when given, how it frees the
    memory in parentheses. Guards the holder text of a refused load."""
    assert str(local.Holder("process 7 python", int(2.5e9), "until it exits")) == "process 7 python (2.5 GB, until it exits)"
    assert str(local.Holder("process 7 python", int(2.5e9))) == "process 7 python (2.5 GB)"


def test_ollama_runner_and_loopback_hosts():
    """An executable of an `ollama` directory, or `ollama` itself, is an Ollama runner; only loopback hosts count
    as this machine's Ollama."""
    assert local.GpuProcess(1, "/usr/local/lib/ollama/llama-server", 0).ollama
    assert local.GpuProcess(1, "/usr/bin/ollama", 0).ollama
    assert not local.GpuProcess(1, "/usr/bin/python3", 0).ollama
    for url in ("http://localhost:11434/api/ps", "http://127.0.0.1:11434/api/ps", "http://[::1]:11434/api/ps"):
        assert local.loopback(url), url
    for url in ("http://gpu-box.example.com:11434/api/ps", "http://10.0.0.5:11434/api/ps"):
        assert not local.loopback(url), url
