"""Stills of a drawn scene's page as its picture versions: listed by /api/project, marked with /api/marked and
changed with a `change` request, never varied."""
from __future__ import annotations

import json
from pathlib import Path

from tests.unit.studio.conftest import PNG, data_url, png
from tests.unit.studio.test_video import STORYBOARD, make_video, video_of, vreq

DRAWN = {"id": "chart", "brief": "A bar chart grows bar by bar.", "narration": ["Cases fell."], "beats": ["bars"]}
BOARD = {**STORYBOARD, "scenes": [*STORYBOARD["scenes"], DRAWN]}


def still(p: Path, n: int, page_version: str = "scenes/chart/v2", name: str = "at_004.000.png",
          data: bytes = PNG, scene: str = "chart", write_png: bool = True) -> Path:
    """Still N of `scene`: the PNG `stills` writes in `<page_version>/stills/` and the sidecar
    `images/<scene>/v<N>.json` that names it."""
    d = p / page_version / "stills"
    d.mkdir(parents=True, exist_ok=True)
    if write_png:
        (d / name).write_bytes(data)
    images = p / "images" / scene
    images.mkdir(parents=True, exist_ok=True)
    (images / f"v{n}.json").write_text(json.dumps({
        "kind": "short-video", "action": "storyboard", "page_version": page_version, "still": name, "t": 4.0,
        "style": "ink", "page_style": {"dimension": "2D", "light": "flat", "typography": "Inter", "camera": "static",
                                       "palette": ["#101820", "#f2f2f2", "#e8a33d"]},
        "model": None, "model_id": None, "prompt": None, "change": None, "source": None, "refs": []}))
    return d / name


def scene_of(client, p: Path, sid: str) -> dict:
    return next(s for s in video_of(client, p)["video"]["scenes"] if s["id"] == sid)


def test_stills_listed(client, studio):
    """A drawn scene's sidecars that name a still of its page are listed among its pictures, newest first, with
    `image` the still in the page version and `still` the newest; a sidecar whose still is missing, whose page
    version or still name is not a page's, or whose stills/ is a symbolic link is left out. A scene with a picture
    has `still` null. Guards the storyboard card and the picture area of an HTML scene."""
    p = make_video(studio.root, storyboard=BOARD)
    first = still(p, 1, "scenes/chart/v1")
    second = still(p, 2, "scenes/chart/v2")
    still(p, 3, "scenes/chart/v3", write_png=False)
    still(p, 4, "../outside/v1")
    still(p, 5, "scenes/chart/v4", name="sheet.png")
    target = p / "elsewhere"
    target.mkdir()
    (target / "at_001.000.png").write_bytes(PNG)
    (p / "scenes" / "chart" / "v5").mkdir()
    (p / "scenes" / "chart" / "v5" / "stills").symlink_to(target)
    still(p, 6, "scenes/chart/v5", name="at_001.000.png", write_png=False)
    scene = scene_of(client, p, "chart")
    assert [(v["n"], v["image"]) for v in scene["pictures"]] == [(2, str(second)), (1, str(first))]
    assert (scene["still"], scene["picture"]) == (2, None)
    assert scene["pictures"][0]["page_style"]["dimension"] == "2D"
    assert scene_of(client, p, "injection")["still"] is None


def test_world_still_listed(client, studio):
    """A still of a world scene names its world version and the scene-prefixed still. Guards HTML scenes of a
    world."""
    world = {**DRAWN, "world": "lab", "length": 4}
    world.pop("narration")
    p = make_video(studio.root, storyboard={**STORYBOARD, "scenes": [world]}, pictures={})
    f = still(p, 1, "worlds/lab/v3", name="chart_at_002.500.png")
    scene = scene_of(client, p, "chart")
    assert (scene["still"], scene["pictures"][0]["image"]) == (1, str(f))


def test_still_change(client, studio):
    """A still takes a `change` with a note or with the marked copy and mask /api/marked writes at the still's size;
    `variations` and `other-styles` of a still are refused, as is a change of a sidecar whose still is missing.
    Guards feedback on an HTML scene's still."""
    p = make_video(studio.root, storyboard=BOARD)
    still(p, 1, data=png(8, 6))
    still(p, 2, "scenes/chart/v3", write_png=False)
    note = vreq(p, "change", scene="chart", version=1, note="bigger labels", marks=[], marked=None, mask=None)
    assert client.post("/api/request", note)[0] == 202
    status, body = client.post("/api/marked", {"project": str(p), "scene": "chart", "version": 1,
                                               "png": data_url(), "mask": data_url(png(8, 6))})
    assert status == 200
    marks = p / "images" / "chart" / "marks"
    assert (body["path"], body["mask"]) == (str(marks / "v1-marked-1.png"), str(marks / "v1-mask-1.png"))
    assert client.post("/api/marked", {"project": str(p), "scene": "chart", "version": 1, "png": data_url(),
                                       "mask": data_url(png(4, 4))})[0] == 400
    assert client.post("/api/marked", {"project": str(p), "scene": "chart", "version": 2, "png": data_url()})[0] == 400
    marked = vreq(p, "change", scene="chart", version=1, note="", marks=[
        {"n": 1, "kind": "box", "comment": "move left", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
        marked=body["path"], mask=body["mask"])
    assert client.post("/api/request", marked)[0] == 202
    for bad in (vreq(p, "variations", scene="chart", version=1, count=3),
                vreq(p, "other-styles", scene="chart", version=1, styles=[]),
                {**note, "version": 2}):
        assert client.post("/api/request", bad)[0] == 400, bad


def test_use_still(client, studio):
    """A `use-still` request names a drawn scene and one of its stills; a version that is a picture (no
    `page_version`), a missing version or a still whose PNG is missing is refused. Guards "Use this still"."""
    p = make_video(studio.root, storyboard=BOARD)
    still(p, 1, "scenes/chart/v1")
    still(p, 2, "scenes/chart/v2")
    still(p, 3, "scenes/chart/v3", write_png=False)
    status, body = client.post("/api/request", vreq(p, "use-still", scene="chart", version=1))
    assert status == 202, body
    for bad in (vreq(p, "use-still", scene="injection", version=1),
                vreq(p, "use-still", scene="chart", version=3),
                vreq(p, "use-still", scene="chart", version=9),
                vreq(p, "use-still", scene="nope", version=1)):
        assert client.post("/api/request", bad)[0] == 400, bad


def test_use_style_takes_an_earlier_style_sample(client, studio):
    """`use-style` with a version takes any still of the samples' scene that carries a page_style, also one from an
    earlier round of samples, and, once no samples wait, any such still of the key scene (the first drawn scene
    here); a still without page_style, a picture or a missing version is refused. Guards choosing a style from the
    first round of samples after `style-samples` made a second (studio:videos SKILL.md, use-style)."""
    drawn_only = {**STORYBOARD, "scenes": [DRAWN, {"id": "morph", "engine": "clip"}]}
    p = make_video(studio.root, storyboard=drawn_only, pictures={},
                   meta={"samples": {"scene": "chart", "versions": [4, 5, 6], "style": "invent"}})
    for n in range(1, 7):
        still(p, n, f"scenes/chart/v{n}")
    plain = json.loads((p / "images" / "chart" / "v3.json").read_text())
    del plain["page_style"]
    (p / "images" / "chart" / "v3.json").write_text(json.dumps(plain))
    for n in (1, 2, 5):
        assert client.post("/api/request", vreq(p, "use-style", version=n))[0] == 202, n
    for n in (3, 9):
        assert client.post("/api/request", vreq(p, "use-style", version=n))[0] == 400, n
    chosen = make_video(studio.root, "chosen", storyboard=drawn_only, pictures={})
    still(chosen, 1, "scenes/chart/v1")
    assert client.post("/api/request", vreq(chosen, "use-style", version=1))[0] == 202
    assert client.post("/api/request", vreq(chosen, "use-style", version=2))[0] == 400
