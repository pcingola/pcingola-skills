"""Memory safety of local models: the weight sum, the allocator cap and the process lock (docs/ai_models.md,
Local models). Each case that sets a cap or takes the lock runs in a child process, because both last for the
life of the process."""

import subprocess
import sys
import textwrap
import time

import pytest
import torch

from ai_models import AIModelsError, local
from tests.prereq import requires
from tests.subproc import child_env, run_python


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


@requires(torch.cuda.is_available(), "a CUDA GPU (the allocator cap is CUDA only)")
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
    """, child_env(SKILLS_CONFIG=str(tmp_path / "none.yaml")))
    assert done.returncode == 0, done.stderr
    assert "refused: local model some/model: it ran out of memory" in done.stdout


HOLDER = """
    import sys
    from ai_models import local
    local.hold_lock()
    print("held", flush=True)
    sys.stdin.readline()
"""


REFUSED = """
    import sys
    from ai_models import local
    try:
        local.pipeline("no-such/repo")
    except Exception as e:
        print("refused", type(e).__name__, flush=True)
    sys.stdin.readline()
"""


def start(code: str, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", textwrap.dedent(code)], env=env, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def lock_env(tmp_path) -> dict[str, str]:
    """A child environment whose temporary directory, and so the lock file, is `tmp_path`; offline, with no config."""
    return child_env(TMPDIR=str(tmp_path), TEMP=str(tmp_path), TMP=str(tmp_path), HF_HUB_OFFLINE="1",
                     SKILLS_CONFIG=str(tmp_path / "none.yaml"))


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
            first.wait(timeout=30)
            out, err = second.communicate("\n", timeout=30)
            assert out.strip() == "held", err
            assert f"waiting for process {first.pid}," in err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait()
    assert (tmp_path / local.LOCK_FILE).exists()


def test_refused_load_releases_the_lock(tmp_path):
    """Guards against a process that holds the lock forever without a model: a load that fails while the process
    has no pipeline releases the lock, so another process takes it at once."""
    env = lock_env(tmp_path)
    first = start(REFUSED, env)
    try:
        assert first.stdout.readline().startswith("refused"), first.stderr.read()
        second = start(HOLDER, env)
        try:
            out, err = second.communicate("\n", timeout=60)
            assert out.strip() == "held", err
            assert "waiting" not in err
        finally:
            second.kill()
    finally:
        first.kill()
        first.wait()
