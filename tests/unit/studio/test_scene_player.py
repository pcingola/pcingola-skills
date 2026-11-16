"""The scene player's server side: the `world` and `length` storyboard keys, the render's page in /api/project, the
`/scene/` route with its Host and Origin checks, `/api/scene-marked`, the `mark-scene` request and comments.json.
Behaviour: section 3 of tmp/plans/animation_in_short_video_design.md ("Studio: point and comment on a playing
scene") and its sections 1 and 2 for the storyboard keys."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_server.comments import CommentState, CommentStore
from studio_server.video import SCENE_PREFIX, check_storyboard

from .conftest import data_url, png
from .scene_project import make_scene_project


def _html(id: str = "s", **kw) -> dict:
    return {"id": id, "brief": "b", "narration": ["One."], "beats": ["one"], **kw}


def _sb(*scenes: dict) -> dict:
    return {"title": "T", "topic": "t", "scenes": list(scenes)}


VALID = [
    _sb(_html("a", world="city"), _html("b", world="city"), _html("c")),
    _sb(_html("a", world="city", engine="html"), _html("b", world="city")),
    _sb({"id": "a", "brief": "b", "length": 6}),
    _sb({"id": "a", "brief": "b", "length": 2.5, "world": "w"}, _html("b", world="w")),
]
INVALID = [
    _sb(_html("a", world="city"), _html("b"), _html("c", world="city")),
    _sb(_html("a", world="City-1")),
    _sb(_html("a", world="w", image="a.png")),
    _sb({"id": "a", "template": "title", "narration": ["Hi."], "beats": ["hi"], "world": "w"}),
    _sb(_html("a", world="w", engine="manim")),
    _sb(_html("a", length=6)),
    _sb({"id": "a", "brief": "b", "length": 0}),
    _sb({"id": "a", "brief": "b", "length": "6"}),
    _sb({"id": "a", "brief": "b", "engine": "video", "image": "a.png", "length": 6}),
    _sb({"id": "a", "brief": "b"}),
]


@pytest.mark.parametrize("storyboard", VALID)
def test_world_and_length_accepted(storyboard):
    """Consecutive world scenes of the html engine, and a silent HTML scene with `length` and no narration, pass the
    server's storyboard check. Guards the page's writes of such storyboards."""
    assert check_storyboard(storyboard) == []


@pytest.mark.parametrize("storyboard", INVALID)
def test_world_and_length_refused(storyboard):
    """A world split by another scene, a bad world name, a world scene with an image, template or other engine,
    `length` with narration, not positive, not a number or on another engine, and a scene with neither narration
    nor `length` are refused. Guards storyboards media:short-video cannot render."""
    assert check_storyboard(storyboard)


def test_clip_has_its_page(client, studio):
    """/api/project gives an HTML render's page path, its /scene/ URL, start 0, no world, and the narration it was
    rendered with; a cut of a world render points at the world's page and start. Guards the page's choice between
    the scene player and the <video>."""
    p = make_scene_project(studio.root)
    status, d = client.get(f"/api/project?dir={p}")
    clip = next(s for s in d["video"]["scenes"] if s["id"] == "intro")["clip"]
    assert status == 200 and clip["n"] == 1
    assert clip["page"] == str(p / "scenes" / "intro" / "v1" / "index.html")
    assert clip["page_url"] == f"{SCENE_PREFIX}short-video/check/scenes/intro/v1/index.html"
    assert clip["start"] == 0 and clip["world"] is None and clip["narration"] is None

    w = p / "worlds" / "city" / "v2"
    w.mkdir(parents=True)
    (w / "index.html").write_text("<html></html>")
    v = p / "scenes" / "pic" / "v1"
    v.mkdir(parents=True)
    voice = p / "voice" / "pic" / "v3"
    voice.mkdir(parents=True)
    (voice / "narration.wav").write_bytes(b"RIFF")
    (v / "meta.json").write_text(json.dumps({"duration": 2.0, "voice_version": "v3", "world": "city"}))
    (v / "world.json").write_text(json.dumps({"world": "city", "version": "v2", "start": 3.0, "duration": 2.0}))
    _, d = client.get(f"/api/project?dir={p}")
    clip = next(s for s in d["video"]["scenes"] if s["id"] == "pic")["clip"]
    assert clip["page_url"] == f"{SCENE_PREFIX}short-video/check/worlds/city/v2/index.html"
    assert clip["start"] == 3.0 and clip["world"] == "city"
    assert clip["narration"] == str(voice / "narration.wav")


def test_scene_route(client, studio, page):
    """/scene/ serves the files of a scene version with nosniff and a sandbox CSP; index.html gets scene-player.js
    inlined before </body> and stays unchanged on disk. Guards the iframe's page and its relative URLs."""
    (page / "scene-player.js").write_text("window.PLAYER = 1;")
    p = make_scene_project(studio.root)
    index = p / "scenes" / "intro" / "v1" / "index.html"
    before = index.read_bytes()
    status, headers, body = client.call("GET", f"{SCENE_PREFIX}short-video/check/scenes/intro/v1/index.html")
    assert status == 200 and headers["content-type"] == "text/html; charset=utf-8"
    assert headers["content-security-policy"] == "sandbox allow-scripts"
    assert headers["x-content-type-options"] == "nosniff"
    assert body.index(b"window.PLAYER = 1;") < body.rindex(b"</body>")
    assert index.read_bytes() == before
    status, headers, body = client.call("GET", f"{SCENE_PREFIX}short-video/check/scenes/intro/v1/gsap.min.js")
    assert status == 200 and body == b"/* gsap */" and headers["content-security-policy"] == "sandbox allow-scripts"
    assert headers["access-control-allow-origin"] == "*"


def test_scene_route_ranges(client, studio, page):
    """/scene/ answers a Range header of a scene file with 206 and the bytes, and a range outside the file with 416;
    a whole file says accept-ranges. Guards the seek of a <video data-start> in the scene page."""
    p = make_scene_project(studio.root, mp4=bytes(range(100)))
    url = f"{SCENE_PREFIX}short-video/check/scenes/intro/v1/scene.mp4"
    status, headers, body = client.call("GET", url)
    assert status == 200 and headers["accept-ranges"] == "bytes" and body == bytes(range(100))
    status, headers, body = client.call("GET", url, headers={"range": "bytes=10-19"})
    assert status == 206 and body == bytes(range(10, 20)) and headers["content-range"] == "bytes 10-19/100"
    assert headers["access-control-allow-origin"] == "*"
    assert client.call("GET", url, headers={"range": "bytes=200-"})[0] == 416


def test_scene_route_refusals(client, studio, page, tmp_path):
    """/scene/ serves nothing outside a version directory of a short-video project: no traversal, hidden file,
    symbolic link, other top directory or project kind. Guards project files against the sandboxed page."""
    (page / "scene-player.js").write_text("")
    p = make_scene_project(studio.root)
    v = p / "scenes" / "intro" / "v1"
    (tmp_path / "secret.txt").write_text("secret")
    (v / "link.txt").symlink_to(tmp_path / "secret.txt")
    (v / ".hidden").write_text("x")
    (p / "scenes" / "intro" / "v2").symlink_to(v)
    base = f"{SCENE_PREFIX}short-video/check"
    for path in (f"{base}/scenes/intro/v1/../../../project.json", f"{base}/scenes/intro/v1/%2e%2e/meta.json",
                 f"{base}/scenes/intro/v1/..%2f..%2fproject.json", f"{base}/scenes/intro/v1/link.txt",
                 f"{base}/scenes/intro/v1/.hidden", f"{base}/scenes/intro/v2/index.html",
                 f"{base}/images/intro/v1/index.html", f"{SCENE_PREFIX}images/check/scenes/intro/v1/index.html",
                 f"{base}/scenes/intro/latest/index.html", f"{base}/project.json", f"{base}/scenes/intro/v1/"):
        status, _, body = client.call("GET", path)
        assert status == 403, path
        assert b"secret" not in body
    assert client.call("GET", f"{base}/scenes/intro/v1/missing.js")[0] == 404


def test_scene_route_host_and_origin(client, studio, page):
    """The Host check holds for /scene/; a cross-site GET is allowed only under /scene/<token>/ (the sandboxed page
    loads its scripts with an opaque origin); another token or none is 404; a POST from the sandbox (Origin null) is
    refused. Guards against DNS rebinding, another site reading scene files, and the scene page sending requests."""
    (page / "scene-player.js").write_text("")
    p = make_scene_project(studio.root)
    rel = "short-video/check/scenes/intro/v1/gsap.min.js"
    url = f"{SCENE_PREFIX}{rel}"
    assert client.call("GET", url, headers={"host": f"evil.example:{studio.port}"})[0] == 403
    assert client.call("GET", url, headers={"sec-fetch-site": "cross-site"})[0] == 200
    for other in (f"/scene/{rel}", f"/scene/wrongtoken/{rel}"):
        status, _, body = client.call("GET", other, headers={"sec-fetch-site": "cross-site"})
        assert status == 404 and b"gsap" not in body, other
    assert client.call("GET", "/api/projects?kind=short-video", headers={"sec-fetch-site": "cross-site"})[0] == 403
    body = {"project": str(p), "scene": "intro", "version": 1, "t": 1.0, "png": data_url(png(4, 4))}
    assert client.post("/api/scene-marked", body, headers={"origin": "null"})[0] == 403
    assert client.post("/api/request", {"kind": "short-video", "action": "message", "text": "x"},
                       headers={"origin": "null"})[0] == 403


def _mark_scene(p: Path, still: str, **kw) -> dict:
    return {"kind": "short-video", "action": "mark-scene", "project": str(p), "scene": "intro", "version": 1,
            "t": 1.5, "world": None, "world_t": None, "mark": {"rect": {"x": 10, "y": 20, "w": 300, "h": 100}},
            "ids": ["label", "box"], "marked": still, "text": "Make the label larger.", **kw}


def test_mark_scene_flow(client, studio, emitted):
    """/api/scene-marked writes comments/<scene>/v<N>-t<t>-<k>.png; a mark-scene request naming it is passed to the
    mod with world null and appended to comments.json as open; a `done` event of that request marks it done.
    Guards the prompt's fields and the comment's state."""
    p = make_scene_project(studio.root)
    body = {"project": str(p), "scene": "intro", "version": 1, "t": 1.5, "png": data_url(png(8, 6))}
    status, answer = client.post("/api/scene-marked", body)
    marked = p / "comments" / "intro" / "v1-t1.50-1.png"
    assert status == 200 and answer == {"path": str(marked)} and marked.is_file()
    assert client.post("/api/scene-marked", body)[1]["path"].endswith("v1-t1.50-2.png")

    status, answer = client.post("/api/request", _mark_scene(p, str(marked)))
    assert status == 202
    req = emitted[-1]["request"]
    assert req["action"] == "mark-scene" and req["skill"] == "videos" and req["world"] is None
    assert req["mark"] == {"rect": {"x": 10, "y": 20, "w": 300, "h": 100}} and req["ids"] == ["label", "box"]
    comments = json.loads((p / "comments" / "intro" / "comments.json").read_text())
    assert comments == [{"request": answer["id"], "t": 1.5, "mark": req["mark"], "ids": ["label", "box"],
                         "text": "Make the label larger.", "marked": str(marked), "state": "open"}]
    assert client.call("POST", "/event", {"kind": "done", "id": answer["id"]})[0] == 204
    comments = json.loads((p / "comments" / "intro" / "comments.json").read_text())
    assert comments[0]["state"] == "done"


def test_mark_scene_refused(client, studio):
    """A mark-scene request is refused for a version that is not the newest render, a time outside the scene, a
    mark that is neither a point nor a rectangle, a still outside comments/<scene>/, or no text; /api/scene-marked
    refuses a stale version and a still that is not a PNG. Guards the agent against a comment it cannot place."""
    p = make_scene_project(studio.root)
    _, answer = client.post("/api/scene-marked", {"project": str(p), "scene": "intro", "version": 1, "t": 1.5,
                                                  "png": data_url(png(8, 6))})
    marked = answer["path"]
    other = p / "comments" / "pic"
    other.mkdir(parents=True)
    (other / "v1-t1.50-1.png").write_bytes(png(2, 2))
    for kw in ({"version": 2}, {"t": 3.5}, {"t": -1}, {"mark": {"rect": {"x": 1, "y": 1, "w": 0, "h": 5}}},
               {"mark": {"point": {"x": 1}}}, {"marked": str(other / "v1-t1.50-1.png")}, {"text": " "},
               {"ids": "box"}, {"scene": "nope"}):
        status, body = client.post("/api/request", _mark_scene(p, marked, **kw))
        assert status == 400, kw
    for kw in ({"version": 2}, {"png": data_url(b"not a png")}, {"t": 9}):
        status, _ = client.post("/api/scene-marked", {"project": str(p), "scene": "intro", "version": 1, "t": 1.0,
                                                      "png": data_url(png(2, 2)), **kw})
        assert status == 400, kw


def test_comment_state_after_restart(client, studio):
    """`done` and `stopped` set the state of an open comment; a store of a later server run finds the comment of an
    earlier request by scanning comments.json. Guards comments left open by a restart or a Stop."""
    p = make_scene_project(studio.root)
    _, answer = client.post("/api/scene-marked", {"project": str(p), "scene": "intro", "version": 1, "t": 1.5,
                                                  "png": data_url(png(8, 6))})
    first = client.post("/api/request", _mark_scene(p, answer["path"]))[1]["id"]
    second = client.post("/api/request", _mark_scene(p, answer["path"]))[1]["id"]
    assert client.call("POST", "/event", {"kind": "stopped", "id": first})[0] == 204
    path = p / "comments" / "intro" / "comments.json"
    assert [c["state"] for c in json.loads(path.read_text())] == ["stopped", "open"]

    later = CommentStore(studio.root)
    assert later.files == {}
    assert later.mark(second, CommentState.DONE)
    assert [c["state"] for c in json.loads(path.read_text())] == ["stopped", "done"]
    assert not later.mark("nosuchrequest", CommentState.DONE)
