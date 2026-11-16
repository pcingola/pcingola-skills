"""Studio on an HTML-first short-video project: a scene's latest page in /api/project with or without a render, the
`mark-scene` request on a page version with no render (no marked still), and the HTML films with their /file
answer. Behaviour: the item "Studio works on a scene that has a page and no render" of tmp/plans/html_film_quality.md."""
from __future__ import annotations

import json
from pathlib import Path

from studio_server.video import SCENE_PREFIX

from .conftest import data_url, png
from .scene_project import SCENE_HTML, make_scene_project


def _scene(d: dict, sid: str) -> dict:
    return next(s for s in d["video"]["scenes"] if s["id"] == sid)


def _page_version(p: Path, n: int, duration: float | None = 4.0, voice: str | None = None) -> Path:
    """`scenes/intro/v<n>/` with index.html (root data-duration `duration`, none when None) and timing.json, no
    render."""
    v = p / "scenes" / "intro" / f"v{n}"
    v.mkdir(parents=True)
    html = SCENE_HTML % {"id": "intro", "duration": duration or 3}
    if duration is None:
        html = html.replace('data-duration="3"', "")
    (v / "index.html").write_text(html, encoding="utf-8")
    (v / "timing.json").write_text(json.dumps({"duration": 2.5, "sentences": []}))
    if voice:
        (v / "voice_version").write_text(voice + "\n")
    return v


def test_page_with_and_without_render(client, studio):
    """A rendered page version gives `video` and the render's duration; a newer page version with no render becomes
    the scene's page with `video` null, its duration from the root's data-duration, else timing.json, and the
    narration of its voice_version. Guards the scene player opening on a scene that has a page and no render."""
    p = make_scene_project(studio.root)
    _, d = client.get(f"/api/project?dir={p}")
    page = _scene(d, "intro")["page"]
    v1 = p / "scenes" / "intro" / "v1"
    assert isinstance(page.pop("created"), str)
    assert page == {"n": 1, "page": str(v1 / "index.html"),
                    "page_url": f"{SCENE_PREFIX}short-video/check/scenes/intro/v1/index.html", "start": 0,
                    "duration": 3.0, "world": None, "narration": None, "video": str(v1 / "scene.mp4")}

    voice = p / "voice" / "intro" / "v2"
    voice.mkdir(parents=True)
    (voice / "narration.wav").write_bytes(b"RIFF")
    _page_version(p, 2, duration=4.0, voice="v2")
    _, d = client.get(f"/api/project?dir={p}")
    scene = _scene(d, "intro")
    assert scene["clip"]["n"] == 1
    assert scene["page"]["n"] == 2 and scene["page"]["video"] is None and scene["page"]["duration"] == 4.0
    assert scene["page"]["page_url"].endswith("/scenes/intro/v2/index.html")
    assert scene["page"]["narration"] == str(voice / "narration.wav")

    _page_version(p, 3, duration=None)
    _, d = client.get(f"/api/project?dir={p}")
    assert _scene(d, "intro")["page"]["n"] == 3 and _scene(d, "intro")["page"]["duration"] == 2.5
    assert _scene(d, "pic")["page"] is None


def test_world_page(client, studio):
    """A world scene's page is the newest world version holding index.html and a world.json naming the scene, with
    its start and duration; `video` is the scene.mp4 of a render cut from that world version, and null once a newer
    world version exists. A scene of another engine has no page. Guards world scenes in the scene player."""
    p = make_scene_project(studio.root)
    (p / "storyboard.json").write_text(json.dumps({"title": "T", "topic": "t", "scenes": [
        {"id": "a", "brief": "b", "length": 2, "world": "city"},
        {"id": "b", "brief": "b", "length": 3, "world": "city"},
        {"id": "m", "brief": "b", "length": 3, "engine": "manim"}]}))
    w1 = p / "worlds" / "city" / "v1"
    w1.mkdir(parents=True)
    (w1 / "index.html").write_text("<html></html>")
    plan = {"world": "city", "duration": 5.0, "fps": 30, "scenes": [
        {"id": "a", "start": 0.0, "duration": 2.0, "frames": [0, 60], "voice_version": None},
        {"id": "b", "start": 2.0, "duration": 3.0, "frames": [60, 150], "voice_version": None}]}
    (w1 / "world.json").write_text(json.dumps(plan))
    cut = p / "scenes" / "b" / "v1"
    cut.mkdir(parents=True)
    (cut / "scene.mp4").write_bytes(b"mp4")
    (cut / "meta.json").write_text(json.dumps({"duration": 3.0, "world": "city", "world_version": "v1"}))
    _, d = client.get(f"/api/project?dir={p}")
    page = _scene(d, "b")["page"]
    assert page["n"] == 1 and page["world"] == "city" and page["start"] == 2.0 and page["duration"] == 3.0
    assert page["page_url"] == f"{SCENE_PREFIX}short-video/check/worlds/city/v1/index.html"
    assert page["video"] == str(cut / "scene.mp4") and _scene(d, "a")["page"]["video"] is None
    assert _scene(d, "m")["page"] is None

    w2 = p / "worlds" / "city" / "v2"
    w2.mkdir()
    (w2 / "index.html").write_text("<html></html>")
    (w2 / "world.json").write_text(json.dumps(plan))
    _, d = client.get(f"/api/project?dir={p}")
    assert _scene(d, "b")["page"]["n"] == 2 and _scene(d, "b")["page"]["video"] is None


def _mark_scene(p: Path, **kw) -> dict:
    return {"kind": "short-video", "action": "mark-scene", "project": str(p), "scene": "intro", "version": 2,
            "t": 1.5, "world": None, "world_t": None, "mark": {"point": {"x": 10, "y": 20}}, "ids": [],
            "marked": None, "text": "Move it left.", **kw}


def test_mark_scene_without_render(client, studio, emitted):
    """On a page version with no render, a mark-scene request without a still is accepted with `marked` null and
    appended to comments.json (its directory made); the earlier rendered version is no longer the one to comment
    on, a time past the page's length is refused, and /api/scene-marked refuses the version with no render. Guards
    the agent getting a request it makes the still for with `stills`."""
    p = make_scene_project(studio.root)
    _page_version(p, 2, duration=4.0)
    status, answer = client.post("/api/request", _mark_scene(p))
    assert status == 202
    req = emitted[-1]["request"]
    assert req["marked"] is None and req["version"] == 2 and req["world"] is None
    comments = json.loads((p / "comments" / "intro" / "comments.json").read_text())
    assert [(c["request"], c["marked"], c["state"]) for c in comments] == [(answer["id"], None, "open")]
    assert client.post("/api/request", _mark_scene(p, t=3.9))[0] == 202
    for kw in ({"version": 1}, {"t": 4.5}):
        assert client.post("/api/request", _mark_scene(p, **kw))[0] == 400, kw
    status, _ = client.post("/api/scene-marked", {"project": str(p), "scene": "intro", "version": 2, "t": 1.0,
                                                  "png": data_url(png(2, 2))})
    assert status == 400


def test_html_film(client, studio):
    """/api/project lists the HTML films newest first with the end of their last segment; /file serves a film.html
    with a CSP that lets its scripts run in a sandbox, and any other HTML file of the project with a plain sandbox.
    Guards the film link of the films step."""
    p = make_scene_project(studio.root)
    for n in (1, 2):
        v = p / "film" / "html" / f"v{n}"
        v.mkdir(parents=True)
        (v / "film.html").write_text("<script>1</script>")
        (v / "manifest.json").write_text(json.dumps({"segments": [
            {"kind": "page", "start": 0, "duration": 3.0}, {"kind": "page", "start": 3.0, "duration": 2.5 * n}],
            "bytes": 18}))
    _, d = client.get(f"/api/project?dir={p}")
    films = d["video"]["html_films"]
    assert [(f["n"], f["path"], f["duration"]) for f in films] == [
        (2, str(p / "film" / "html" / "v2" / "film.html"), 8.0), (1, str(p / "film" / "html" / "v1" / "film.html"), 5.5)]
    status, headers, _ = client.call("GET", f"/file?path={films[0]['path']}")
    assert status == 200 and headers["content-security-policy"] == "sandbox allow-scripts"
    other = p / "film" / "html" / "v1" / "other.html"
    other.write_text("<p></p>")
    status, headers, _ = client.call("GET", f"/file?path={other}")
    assert status == 200 and headers["content-security-policy"] == "sandbox"
