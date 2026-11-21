"""The local-model lock after a refused load (docs/ai_models.md, Local model memory): a load that fails while the
process has no model releases the lock. Each case runs in a child process, because the lock lasts for the life of
the process. No case loads a model."""
from tests.local_lock import HOLDER, lock_env, start


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
        first.wait(timeout=5)
