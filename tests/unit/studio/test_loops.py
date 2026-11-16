"""Unit tests of the studio server's heartbeat, parent watch, change polling loop and start-up."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


import studio_server
from studio_server.__main__ import DEFAULT_ROOT
from studio_server.server import Heartbeat, watch_heartbeat, watch_parent, watch_projects

from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python

from .conftest import make_project

SERVER_DIR = Path(studio_server.__file__).resolve().parents[1]


def test_heartbeat_counts_from_start():
    """Without any heartbeat the timeout runs from creation; each beat restarts it. Guards the exit after the
    timeout without the mod."""
    hb = Heartbeat(0.2)
    assert not hb.expired()
    time.sleep(0.25)
    assert hb.expired()
    hb.beat()
    assert not hb.expired()


def test_heartbeat_endpoint(client, studio):
    """POST /heartbeat restarts the timeout. Guards the mod keeping the server alive."""
    before = studio.heartbeat.last
    time.sleep(0.01)
    assert client.post("/heartbeat")[0] == 204
    assert studio.heartbeat.last > before
    assert not studio.heartbeat.expired()


def test_watch_heartbeat_exits():
    """The heartbeat loop calls exit once the timeout passed. Guards the exit itself."""
    hb = Heartbeat(0.01)
    codes = []
    time.sleep(0.02)
    watch_heartbeat(hb, codes.append, interval=0)
    assert codes == [0]


def test_watch_parent_exits_when_parent_gone():
    """The parent loop exits when the process that started the wrapper is gone. Guards the fast exit when Claude
    Code ends (uv run sits between it and Python, so the server's own parent id does not change)."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    codes = []
    watch_parent(child.pid, codes.append, interval=0)
    assert codes == [0]


def test_watch_parent_keeps_running_while_parent_lives():
    """With the parent alive the loop does not exit. Guards against exiting under a living session."""
    codes = []
    t = threading.Thread(target=watch_parent, args=(os.getpid(), codes.append, 0.01), daemon=True)
    t.start()
    t.join(0.3)
    assert t.is_alive() and codes == []


def test_watch_projects_loop(studio, events):
    """The polling loop broadcasts change notices without being called by hand. Guards the background watcher."""
    ev = events()
    studio.poll()
    stop = threading.Event()
    t = threading.Thread(target=watch_projects, args=(studio, 0.05, stop), daemon=True)
    t.start()
    try:
        make_project(studio.root, "dog")
        assert ev.next() == {"kind": "projects", "project_kind": "image"}
    finally:
        stop.set()
        t.join(1)


IMPORT = "from studio_server.__main__ import projects_root"


def studio_env(tmp_path: Path, studio_dir: str | None = None, **extra: str) -> dict[str, str]:
    """A child environment with HOME and CLAUDE_PLUGIN_DATA in `tmp_path` and a config.yaml that sets
    `studio.dir` to `studio_dir` (no setting when None)."""
    sections = {} if studio_dir is None else {"studio": {"dir": studio_dir}}
    cfg = write_config(tmp_path / "config.yaml", **sections)
    return child_env({"HOME": str(tmp_path / "home"), "CLAUDE_PLUGIN_DATA": str(tmp_path / "pd"),
                      "SKILLS_CONFIG": str(cfg), **extra})


def test_projects_root_default_and_setting(tmp_path):
    """`studio.dir` is read from config.yaml, `~` expanded; unset, the root is ~/Documents/Studio. Guards the
    setting."""
    home = tmp_path / "home"
    assert DEFAULT_ROOT == Path.home() / "Documents/Studio"
    assert py_value(IMPORT, "projects_root()", studio_env(tmp_path)) == str(home / "Documents/Studio")
    for value, expected in (("/tmp/somewhere", "/tmp/somewhere"), ("~/Pictures/Studio", str(home / "Pictures/Studio"))):
        assert py_value(IMPORT, "projects_root()", studio_env(tmp_path, value)) == expected


def test_projects_root_ignores_the_environment(tmp_path):
    """A process variable STUDIO_DIR is ignored, with and without `studio.dir` in config.yaml. Guards
    config.yaml as the only source of the setting."""
    assert py_value(IMPORT, "projects_root()", studio_env(tmp_path, STUDIO_DIR="/from/process")) == str(
        tmp_path / "home" / "Documents/Studio")
    env = studio_env(tmp_path, "/from/file", STUDIO_DIR="/from/process")
    assert py_value(IMPORT, "projects_root()", env) == "/from/file"


def test_relative_root_refused(tmp_path):
    """A relative or blank `studio.dir` exits non-zero with a message naming the setting. Guards a root that would
    depend on
    the directory the server was started in."""
    for value in ("Documents/Studio", "  "):
        done = run_python(f"{IMPORT}\nprojects_root()", studio_env(tmp_path, value))
        assert done.returncode not in (0, None)
        assert "studio.dir" in done.stderr, done.stderr


def test_main_prints_ready(tmp_path):
    """`python -m studio_server` creates the root, prints the ready line and serves on it; it exits when the
    process named by --parent-pid is gone. Guards the start-up the mod waits for."""
    root = tmp_path / "Studio"
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    cfg = write_config(tmp_path / "config.yaml", studio={"dir": str(root)})
    env = {**child_env(SKILLS_CONFIG=str(cfg)), "PYTHONPATH": str(SERVER_DIR)}
    assert env["CLAUDE_PLUGIN_DATA"] != os.environ.get("CLAUDE_PLUGIN_DATA")  # the user's settings stay hidden
    proc = subprocess.Popen([sys.executable, "-m", "studio_server", "--parent-pid", str(parent.pid)],
                            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, text=True)
    try:
        ready = json.loads(proc.stdout.readline())
        assert ready["type"] == "ready" and ready["url"].startswith("http://127.0.0.1:")
        with urllib.request.urlopen(ready["url"] + "/api/config", timeout=5) as r:
            assert json.loads(r.read())["root"] == str(root.resolve())
        assert (root / "images").is_dir()
        parent.kill()
        parent.wait()
        assert proc.wait(timeout=10) == 0
    finally:
        parent.kill()
        proc.kill()
        proc.wait()
