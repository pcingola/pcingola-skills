"""Memory safety of local models on the GPU: the allocator cap, the release of the lock after a refused load, the
free memory after a holder exits, the processes named in a memory error and the wait for Ollama
(docs/ai_models.md, Local models). Each case that sets a cap or takes the lock runs in a child process, because
both last for the life of the process. No case loads a model."""

import os
import shutil
import subprocess
import sys
import textwrap
import time

import pytest
import torch

from ai_models import config, local
from tests.local_lock import HOLDER, lock_env, start
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG
from tests.subproc import child_env, run_python

NEEDS_CUDA = requires(torch.cuda.is_available(), "a CUDA GPU")


@pytest.fixture(autouse=True)
def _config():
    """The in-process memory queries read the Ollama providers of tests/config.yaml, never the user's config."""
    config.use(TEST_CONFIG)
    yield
    config.use(None)


@NEEDS_CUDA
def test_allocation_over_the_cap_raises_ai_models_error(tmp_path):
    """Guards the cap: with the allocator capped below one allocation, the allocation raises the AIModelsError
    instead of growing into memory other processes need."""
    done = run_python("""
        import torch
        from ai_models import AIModelsError, local
        local.cap_memory("cuda", 2**20)
        try:
            with local.out_of_memory("some/model"):
                torch.empty(2**30, dtype=torch.uint8, device="cuda")
        except AIModelsError as e:
            print("refused:", e)
    """, child_env(SKILLS_CONFIG=str(tmp_path / "none.yaml")), timeout=25)
    assert done.returncode == 0, done.stderr
    assert "refused: local model some/model: it ran out of memory" in done.stdout


REFUSED = """
    import sys
    from ai_models import local
    try:
        local.pipeline("no-such/repo")
    except Exception as e:
        print("refused", type(e).__name__, flush=True)
    sys.stdin.readline()
"""


def test_refused_load_releases_the_lock(tmp_path):
    """Guards against a process that holds the lock forever without a model: a load that fails while the process
    has no pipeline releases the lock, so another process takes it at once. The load reads the device's free
    memory and caps its allocator before it fails on the missing repo."""
    env = lock_env(tmp_path)
    first = start(REFUSED, env)
    try:
        assert first.stdout.readline().startswith("refused"), first.stderr.read()
        second = start(HOLDER, env)
        try:
            out, err = second.communicate("\n", timeout=20)
            assert out.strip() == "held", err
            assert "waiting" not in err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait()


GPU_HOLDER = """
    import sys, torch
    from ai_models import local
    local.hold_lock()
    x = torch.ones(int(sys.argv[1]), dtype=torch.uint8, device="cuda")
    torch.cuda.synchronize()
    print("held", flush=True)
    sys.stdin.readline()
"""


GPU_WAITER = """
    import sys
    from ai_models import local
    local.hold_lock()
    print(local.wait_for_memory("cuda", int(sys.argv[1])), flush=True)
"""


@NEEDS_CUDA
def test_free_memory_comes_back_after_the_holder_exits(tmp_path):
    """Guards the refused LTX renders: after waiting for a holder of GPU memory, `wait_for_memory` reads the
    memory the holder gave back, within `SETTLE_SECONDS`."""
    env = lock_env(tmp_path)
    before = local.free_memory("cuda")
    size = before // 3
    first = start(GPU_HOLDER, env, str(size))
    try:
        assert first.stdout.readline().strip() == "held", first.stderr.read()
        assert local.free_memory("cuda") < before - size // 2
        need = before - size // 2
        second = start(GPU_WAITER, env, str(need))
        try:
            time.sleep(2)
            first.stdin.close()
            out, err = second.communicate(timeout=20)
            assert int(out) >= need, err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait()


PLAIN_GPU_HOLDER = """
    import sys
    import torch
    x = torch.empty(int(2e9), dtype=torch.uint8, device="cuda")
    x.fill_(1)
    torch.cuda.synchronize()
    print("ready", flush=True)
    sys.stdin.read()
"""


@NEEDS_CUDA
@requires(shutil.which("nvidia-smi"), "nvidia-smi (NVIDIA driver)")
def test_memory_error_names_a_process_that_holds_gpu_memory(tmp_path):
    """Guards the message of a refused load: a process that holds 2 GB of GPU memory is named in `memory_error`
    with its PID and size, and this process is not."""
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(PLAIN_GPU_HOLDER)],
                              env=child_env(SKILLS_CONFIG=str(tmp_path / "none.yaml")),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        uuid = local.device_uuid("cuda")
        assert any(p.pid == holder.pid for p in local.gpu_processes(uuid))
        assert not any(p.pid == holder.pid for p in local.gpu_processes("GPU-00000000-0000-0000-0000-000000000000"))
        held = {h.what: h.size for h in local.memory_holders()}
        name = next((w for w in held if w.startswith(f"process {holder.pid} ")), None)
        assert name, held
        assert held[name] >= 2e9
        assert not any(w.startswith(f"process {os.getpid()} ") for w in held)
        assert f"process {holder.pid} " in str(local.memory_error("some/model", "it needs 9 GB"))
    finally:
        holder.stdin.close()
        holder.wait(20)


@NEEDS_CUDA
def test_wait_for_ollama_returns_at_once_when_memory_is_free():
    """With the need below the free memory, `wait_for_ollama` returns the free memory without waiting."""
    dev = local.device()
    started = time.monotonic()
    assert local.wait_for_ollama(dev, 1) >= 1
    assert time.monotonic() - started < local.OLLAMA_POLL_SECONDS
