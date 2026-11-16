"""A short-video project with rendered HTML scenes, as media:short-video writes them, for the scene player tests."""
from __future__ import annotations

import json
from pathlib import Path

from studio_server.video import default_film

# A minimal scene page in the layout of short-video's scene.html: a root with data-composition-id and one paused
# GSAP timeline in window.__timelines. `title` fades in from 0 to 1 s; `box` moves right from 0 to 2 s.
SCENE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<script src="gsap.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1280px; height: 720px; overflow: hidden; background: #000; }
  #root { position: relative; width: 1280px; height: 720px; overflow: hidden; background: #123; }
  #bg-fill { position: absolute; inset: 0; background: #234; }
  #title { position: absolute; left: 140px; top: 120px; width: 1000px; height: 160px; color: #fff;
           font: bold 96px/160px sans-serif; text-align: center; }
  #box { position: absolute; left: 100px; top: 420px; width: 300px; height: 200px; background: #e8a33d; }
  #label { position: absolute; left: 20px; top: 20px; width: 260px; height: 60px; color: #000;
           font: 32px/60px sans-serif; }
</style>
</head>
<body>
<div id="root" data-composition-id="%(id)s" data-start="0" data-duration="%(duration)s" data-width="1280"
     data-height="720" data-fps="30">
  <div id="bg-fill"></div>
  <h1 id="title">Scene check</h1>
  <div id="box"><span id="label">Label</span></div>
</div>
<script>
  const tl = gsap.timeline({ paused: true });
  tl.fromTo("#title", { opacity: 0 }, { opacity: 1, duration: 1 }, 0);
  tl.fromTo("#box", { x: 0 }, { x: 600, duration: 2, ease: "none" }, 0);
  tl.to({}, { duration: %(duration)s - 2 }, 2);
  window.__timelines = window.__timelines || {};
  window.__timelines["%(id)s"] = tl;
</script>
</body>
</html>
"""

STORYBOARD = {
    "title": "Scene check",
    "topic": "The scene player.",
    "scenes": [
        {"id": "intro", "brief": "A title fades in; a box slides right.", "length": 3},
        {"id": "pic", "image": "pic/v1.png", "brief": "Push in.", "narration": ["One."], "beats": ["one"]},
    ],
}


def make_scene_project(root: Path, gsap: bytes = b"/* gsap */", mp4: bytes = b"mp4", duration: float = 3.0,
                       name: str = "check") -> Path:
    """`<root>/short-video/<name>`: project.json, storyboard.json, and render v1 of the silent HTML scene `intro`
    (index.html, gsap.min.js, scene.mp4, meta.json) made from that page."""
    p = root / "short-video" / name
    v = p / "scenes" / "intro" / "v1"
    v.mkdir(parents=True)
    (p / "project.json").write_text(json.dumps(
        {"name": "Check", "brief": "a film", "kind": "short-video", "created": "2026-11-15T10:00:00+00:00",
         "autonomy": "step", "settings": {}, "film": default_film(), "style": {"name": "ink"}, "scene_styles": {}}))
    (p / "storyboard.json").write_text(json.dumps(STORYBOARD))
    (v / "index.html").write_text(SCENE_HTML % {"id": "intro", "duration": duration}, encoding="utf-8")
    (v / "gsap.min.js").write_bytes(gsap)
    (v / "scene.mp4").write_bytes(mp4)
    (v / "meta.json").write_text(json.dumps({"scene": "intro", "version": "v1", "duration": duration, "fps": 30,
                                             "rendered_at": "2026-11-15T10:01:00+00:00"}))
    return p
