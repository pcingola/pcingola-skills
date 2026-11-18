"""The Studio films step and the reference video upload end to end: the real server and page in headless Chromium on
a short-video project with an HTML film. The newest HTML film plays in a sandboxed iframe, Export MP4 sends an
`export-mp4` request, and a dropped MP4 goes to refs/ and shows in the brief's refs. Behaviour: items 3 and 4 of
tmp/plans/studio_html_scenes.md, `docs/studio.md` (the short-video workspace)."""
from __future__ import annotations

import json
import threading

from studio_server.server import Heartbeat, Studio

from tests.integration.studio.test_scene_player_page import HYPERFRAMES
from tests.prereq import requires
from tests.unit.studio.scene_project import make_scene_project

FILM_HTML = """<!doctype html><html><head><meta charset="utf-8"></head>
<body><div id="out">waiting</div><script>document.getElementById('out').textContent = 'film ran';</script></body></html>
"""


@requires(HYPERFRAMES.is_file(), f"hyperframes in {HYPERFRAMES.parent} (run short-video's setup)")
def test_html_film_export_and_reference_video(tmp_path, page):
    """The films step shows HTML film v1 in an iframe with sandbox allow-scripts whose script runs; Export MP4 sends
    `export-mp4` with the film settings added by the server; an MP4 chosen in step 1 is written to refs/clip.mp4 and
    shown as a video in the refs."""
    emitted: list[dict] = []
    studio = Studio(tmp_path / "Studio", emit=emitted.append, heartbeat=Heartbeat(600.0))
    p = make_scene_project(studio.root)
    v = p / "film" / "html" / "v1"
    v.mkdir(parents=True)
    (v / "film.html").write_text(FILM_HTML, encoding="utf-8")
    (v / "manifest.json").write_text(json.dumps({"segments": [
        {"kind": "page", "start": 0, "duration": 3.0, "scenes": ["intro"], "source": "scenes/intro/v1"}], "bytes": 1}))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    httpd = studio.serve()
    threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True).start()
    studio.poll()
    try:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.add_init_script("if (window === window.top) localStorage.setItem('studio-kind', 'short-video')")
        page.goto(studio.url)
        page.click("#projects button.project")
        frame_el = page.wait_for_selector("#sv-films iframe", state="attached", timeout=30_000)
        assert frame_el.get_attribute("sandbox") == "allow-scripts"
        frame = frame_el.content_frame()
        frame.wait_for_function("document.getElementById('out').textContent === 'film ran'", timeout=30_000)

        page.evaluate("""[...document.querySelectorAll('#sv-films button')]
            .find(b => b.textContent === 'Export MP4').click()""")
        for _ in range(50):
            reqs = [e["request"] for e in emitted if e.get("type") == "request"]
            if reqs:
                break
            page.wait_for_timeout(100)
        assert [r["action"] for r in reqs] == ["export-mp4"]
        assert reqs[0]["film"]["shape"] and reqs[0]["project"] == str(p)

        # The file goes as a buffer: a snap Chromium cannot read files under the system /tmp.
        page.set_input_files("#sv-brief input[type=file]",
                             {"name": "clip.mp4", "mimeType": "video/mp4", "buffer": clip.read_bytes()})
        page.wait_for_selector("#sv-brief .ref video", state="attached", timeout=30_000)
        assert (p / "refs" / "clip.mp4").read_bytes() == clip.read_bytes()
        assert not errors, errors
    finally:
        httpd.shutdown()
        httpd.server_close()
