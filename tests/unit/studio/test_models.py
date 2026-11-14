"""Unit tests of /api/models: the model each image-gen tier and media task resolves to in config.yaml."""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import studio_server
from studio_server.models import TASKS
from studio_server.video import check_storyboard

from tests.settings_env import write_config
from tests.subproc import child_env

from .test_server import gen

SERVER_DIR = Path(studio_server.__file__).resolve().parents[1]
MODELS = {"image": "local:z-image-turbo", "image_edit": "local:flux2-klein-4b", "image_best": "local:z-image-turbo",
          "speech": "azure:gpt-4o-mini-tts", "music": "local:ace-step"}


@contextlib.contextmanager
def server(tmp_path: Path, config: Path):
    """`python -m studio_server` with SKILLS_CONFIG `config`; yields its URL."""
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    env = {**child_env({"HOME": str(tmp_path / "home"), "CLAUDE_PLUGIN_DATA": str(tmp_path / "pd"),
                        "SKILLS_CONFIG": str(config), "STUDIO_DIR": str(tmp_path / "Studio")}),
           "PYTHONPATH": str(SERVER_DIR)}
    proc = subprocess.Popen([sys.executable, "-m", "studio_server", "--parent-pid", str(parent.pid)],
                            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, text=True)
    try:
        yield json.loads(proc.stdout.readline())["url"]
    finally:
        parent.kill()
        proc.kill()
        proc.wait()
        parent.wait()


def get_models(url: str) -> dict:
    with urllib.request.urlopen(url + "/api/models", timeout=5) as r:
        return json.loads(r.read())


def test_endpoint_reads_config(tmp_path):
    """GET /api/models of a real server answers the model of each task and tier of its config.yaml: fast takes
    image without references and image_edit with them; best and multi-ref take one task each. Guards the endpoint,
    the tier mapping the page shows and that it reads the settings file plugin_settings names."""
    cfg = write_config(tmp_path / "config.yaml", models=MODELS)
    with server(tmp_path, cfg) as url:
        got = get_models(url)
    assert got["tasks"] == {t: MODELS.get(t) for t in TASKS}
    assert got["tiers"] == [
        {"id": "best", "model": "local:z-image-turbo", "ref_model": "local:z-image-turbo"},
        {"id": "multi-ref", "model": None, "ref_model": None},
        {"id": "fast", "model": "local:z-image-turbo", "ref_model": "local:flux2-klein-4b"}]


def test_endpoint_without_or_broken_config(tmp_path):
    """A missing config.yaml, or one broken after the server started (the server does not start with a broken
    file), gives every task no model. Guards the page against a 500 when the settings file is absent
    or broken, and that each call reads the file again."""
    with server(tmp_path, tmp_path / "missing.yaml") as url:
        got = get_models(url)
    assert set(got["tasks"].values()) == {None}
    assert not any(t["model"] or t["ref_model"] for t in got["tiers"])
    cfg = write_config(tmp_path / "config.yaml", models=MODELS)
    with server(tmp_path, cfg) as url:
        cfg.write_text("models: [", encoding="utf-8")
        got = get_models(url)
    assert set(got["tasks"].values()) == {None}


def test_request_carries_models(client, emitted):
    """An accepted request carries `models`, the model of each task when it was accepted, so the agent records the
    model and not only the tier. Guards the field the skills read."""
    status, _ = client.post("/api/request", gen(None))
    assert status == 202
    req = emitted[-1]["request"]
    assert set(req["models"]) == set(TASKS)


def test_storyboard_engine_video():
    """A scene with engine video passes the storyboard check; an unknown engine does not. Guards the page's engine
    choice against the server refusing the write."""
    scene = {"id": "a", "brief": "the camera pushes in", "narration": ["One."], "beats": ["One"]}
    assert check_storyboard({"title": "T", "topic": "t", "scenes": [{**scene, "engine": "video"}]}) == []
    assert check_storyboard({"title": "T", "topic": "t", "scenes": [{**scene, "engine": "film"}]})
