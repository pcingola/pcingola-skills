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
from tests.subproc import child_env, run_python

from .test_server import gen

SERVER_DIR = Path(studio_server.__file__).resolve().parents[1]
MODELS = {"image": "local:z-image-turbo", "image_edit": "local:flux2-klein-4b", "image_best": "local:z-image-turbo",
          "speech": "azure:gpt-4o-mini-tts", "music": "local:ace-step"}
# The providers of MODELS: each task names a configured provider, and a diffusers model has an entry.
PROVIDERS = {"local": {"kind": "diffusers", "models": {
                 **{m: {"repo": f"x/{m}"} for m in ("z-image-turbo", "flux2-klein-4b")},
                 "ace-step": {"repo": "x/ace-step", "duration_arg": "audio_duration"}}},
             "azure": {"kind": "azure", "base_url": "https://gateway.example.com", "api_version": "2025-04-01-preview",
                       "api_key": "k"}}


@contextlib.contextmanager
def server(tmp_path: Path, config: Path):
    """`python -m studio_server` with SKILLS_CONFIG `config`; yields its URL."""
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    env = {**child_env({"HOME": str(tmp_path / "home"), "CLAUDE_PLUGIN_DATA": str(tmp_path / "pd"),
                        "SKILLS_CONFIG": str(config)}),
           "PYTHONPATH": str(SERVER_DIR)}
    proc = subprocess.Popen([sys.executable, "-m", "studio_server", "--parent-pid", str(parent.pid)],
                            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, text=True)
    try:
        yield json.loads(proc.stdout.readline())["url"]
    finally:
        parent.kill()
        proc.kill()
        proc.wait(timeout=5)
        parent.wait(timeout=5)


def get_models(url: str) -> dict:
    with urllib.request.urlopen(url + "/api/models", timeout=5) as r:
        return json.loads(r.read())


def test_endpoint_reads_config(tmp_path):
    """GET /api/models of a real server answers the model of each task and tier of its config.yaml: fast takes
    image without references and image_edit with them; best and multi-ref take one task each. Guards the endpoint,
    the tier mapping the page shows and that it reads the settings file plugin_settings names."""
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS, tasks=MODELS)
    with server(tmp_path, cfg) as url:
        got = get_models(url)
    assert got["tasks"] == {t: MODELS.get(t) for t in TASKS}
    assert got["tiers"] == [
        {"id": "best", "model": "local:z-image-turbo", "ref_model": "local:z-image-turbo"},
        {"id": "multi-ref", "model": None, "ref_model": None},
        {"id": "fast", "model": "local:z-image-turbo", "ref_model": "local:flux2-klein-4b"}]


def test_speech_models_from_the_routes(tmp_path):
    """`speech` lists the speech routes: the default (tasks.speech) first, then the configured escalation rows,
    each with what the model takes; a row of a provider without speech models, or not in config.yaml, is left out;
    a malformed routes.md gives no models and its error. Guards the voice picker's choices."""
    cfg = write_config(tmp_path / "config.yaml",
                       providers={"k": {"kind": "kokoro", "models": {"kokoro-v1.0": {
                                      "model_url": "http://127.0.0.1:1/m.onnx", "voices_url": "http://127.0.0.1:1/v.bin",
                                      "langs": {"af_": "en-us"}}}},
                                  "cb": {"kind": "chatterbox", "models": {
                                      "chatterbox-turbo": {"url": "http://127.0.0.1:1", "files": ["a"]}}},
                                  "oai": {"kind": "openai", "api_key": "k"},
                                  "local": {"kind": "diffusers", "models": {"x": {"repo": "x/x"}}}},
                       tasks={"speech": "k:kokoro-v1.0"})
    (tmp_path / "routes.md").write_text(
        "| task | model | when | why |\n|---|---|---|---|\n| speech | k:kokoro-v1.0 | default | calm |\n"
        "| speech | cb:chatterbox-turbo | only when cloned | clones |\n| speech | local:x | only when never | no |\n"
        "| speech | gone:tts | only when never | no |\n| speech | oai:tts | only when styled | styles |\n",
        encoding="utf-8")
    with server(tmp_path, cfg) as url:
        models = get_models(url)
        (tmp_path / "routes.md").write_text("| task | model | when | why |\n|---|---|---|---|\n"
                                            "| speech | kokoro | default | old |\n", encoding="utf-8")
        broken = get_models(url)
    assert broken["speech"] == [] and "is not <provider>:<model>" in broken["speech_error"]
    got = models["speech"]
    assert models["speech_error"] is None
    assert got == [
        {"id": "k:kokoro-v1.0", "default": True, "when": "default", "why": "calm", "voice": "af_heart",
         "speed": [0.5, 2.0], "style": False, "clones": False},
        {"id": "cb:chatterbox-turbo", "default": False, "when": "only when cloned", "why": "clones",
         "voice": "default", "speed": None, "style": False, "clones": True},
        {"id": "oai:tts", "default": False, "when": "only when styled", "why": "styles", "voice": "marin",
         "speed": [0.25, 4.0], "style": True, "clones": False}]


def test_endpoint_without_or_broken_config(tmp_path):
    """A missing config.yaml, or one broken after the server started (the server does not start with a broken
    file), gives every task no model. Guards the page against a 500 when the settings file is absent
    or broken, and that each call reads the file again."""
    with server(tmp_path, tmp_path / "missing.yaml") as url:
        got = get_models(url)
    assert set(got["tasks"].values()) == {None}
    assert not any(t["model"] or t["ref_model"] for t in got["tiers"]) and got["speech"] == []
    assert "no config" in got["speech_error"]
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS, tasks=MODELS)
    with server(tmp_path, cfg) as url:
        cfg.write_text("models: [", encoding="utf-8")
        got = get_models(url)
    assert set(got["tasks"].values()) == {None}


def test_invalid_config_logged_and_reported(tmp_path):
    """read_models with an invalid config.yaml logs the validation error to stderr and answers it in `error`,
    which the page shows when a tier has no model. Guards against an empty model list with no reason."""
    cfg = write_config(tmp_path / "config.yaml", not_a_section={"x": 1})
    done = run_python("""
        import json
        from studio_server.models import read_models
        print(json.dumps(read_models()))
    """, child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert set(got["tasks"].values()) == {None}
    assert "not_a_section" in got["error"]
    assert f"tasks not read: {got['error']}" in done.stderr


def test_valid_config_has_no_error(tmp_path):
    """read_models with a valid config.yaml answers `error` None and logs nothing."""
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS, tasks=MODELS)
    done = run_python("""
        import json
        from studio_server.models import read_models
        print(json.dumps(read_models()))
    """, child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1])["error"] is None
    assert "tasks not read" not in done.stderr


def test_request_carries_models(client, emitted):
    """An accepted request carries `models`, the model of each task when it was accepted, so the agent records the
    model and not only the tier. Guards the field the skills read."""
    status, _ = client.post("/api/request", gen(None))
    assert status == 202
    req = emitted[-1]["request"]
    assert set(req["models"]) == set(TASKS)


def test_storyboard_engine_video():
    """A scene with engine video and an image passes the storyboard check; one without an image, or with an unknown
    engine, does not. Guards the page's engine choice against the server refusing the write, and a video scene with
    no picture to animate."""
    scene = {"id": "a", "image": "a.png", "brief": "the camera pushes in", "narration": ["One."], "beats": ["One"]}
    assert check_storyboard({"title": "T", "topic": "t", "scenes": [{**scene, "engine": "video"}]}) == []
    no_image = {k: v for k, v in scene.items() if k != "image"}
    assert check_storyboard({"title": "T", "topic": "t", "scenes": [{**no_image, "engine": "video"}]})
    assert check_storyboard({"title": "T", "topic": "t", "scenes": [{**scene, "engine": "film"}]})
