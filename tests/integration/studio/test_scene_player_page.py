"""The Studio scene player end to end: the real server and page in headless Chromium on a short-video project with a
rendered HTML scene (GSAP from short-video's node directory, scene.mp4 made with ffmpeg). Chromium is the one
scene renders use (`hyperframes browser path`); every file reaches it over HTTP from the server on 127.0.0.1, so a snap
Chromium that cannot read the system /tmp works. Play, pause, scrub, mark a
box, get the element ids from the player, send; then the marked still, the request, comments.json, the per-comment
Stop, the reload of a newer page version with no render at the same time, and a comment on it sent without a
marked still. Behaviour: section 3 of
tmp/plans/animation_in_short_video_design.md."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from studio_server.server import Heartbeat, Studio

from tests.integration.short_video.wrapper_env import NODE_DIR
from tests.prereq import requires
from tests.unit.studio.scene_project import SCENE_HTML, make_scene_project

GSAP = NODE_DIR / "node_modules" / "gsap" / "dist" / "gsap.min.js"
HYPERFRAMES = NODE_DIR / "node_modules" / ".bin" / "hyperframes"
BACKGROUND = (0x33, 0x55, 0x77)
DURATION = 3.0


def render(path: Path, duration: float = DURATION) -> None:
    """A scene.mp4 of one colour, 1280x720 at 30 fps, as H.264 like media:short-video's renders."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=0x{''.join(f'{c:02x}' for c in BACKGROUND)}:s=1280x720:d={duration}:r=30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def chrome() -> str:
    """The Chromium HyperFrames renders scenes with."""
    done = subprocess.run([str(HYPERFRAMES), "browser", "path"], cwd=NODE_DIR, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


def near(px: tuple, colour: tuple, tol: int = 24) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px[:3], colour))


@requires(GSAP.is_file() and HYPERFRAMES.is_file(), f"gsap and hyperframes in {NODE_DIR} (run short-video's setup)")
@requires(shutil.which("ffmpeg"), "ffmpeg on PATH")
def test_point_and_comment_on_a_playing_scene(tmp_path):
    """The user plays the scene, pauses, scrubs to 1.5 s, drags a box over the label; the player answers the ids
    under it innermost first; Send writes the marked still (the render's frame with the mark) and a mark-scene
    request with the scene, time, mark in frame pixels, ids and still; comments.json holds it open; Stop passes the
    stop to the mod; a newer page version with no render reloads the player at the same time, and a point comment
    on it is sent with `marked` null."""
    emitted: list[dict] = []
    studio = Studio(tmp_path / "Studio", emit=emitted.append, heartbeat=Heartbeat(600.0))
    p = make_scene_project(studio.root, gsap=GSAP.read_bytes(), duration=DURATION)
    render(p / "scenes" / "intro" / "v1" / "scene.mp4")
    httpd = studio.serve()
    threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True).start()
    studio.poll()
    out = tmp_path / "shots"
    out.mkdir()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome())
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept())
            # The sandboxed scene frame has no localStorage; the script runs in the Studio page only.
            page.add_init_script("if (window === window.top) localStorage.setItem('studio-kind', 'short-video')")
            page.goto(studio.url)
            page.click("#projects button.project")
            page.wait_for_selector('[data-result="intro"]', state="attached")
            page.evaluate("""document.querySelector('[data-result="intro"] button[title="Play this scene’s animation"]').click()""")
            page.wait_for_selector("#sv-player .sp-overlay.on", timeout=30_000)
            assert page.locator("#sv-player iframe").get_attribute("sandbox") == "allow-scripts"

            page.click("#sv-player .sp-play")
            page.wait_for_timeout(1200)
            page.click("#sv-player .sp-play")
            played = float(page.locator("#sv-player .sp-time").inner_text().split("/")[0])
            assert 0.5 < played < DURATION, played

            page.evaluate("""(() => { const s = document.querySelector('#sv-player .sp-scrub');
                s.value = '1.5'; s.dispatchEvent(new Event('input')); })()""")
            frame = next(f for f in page.frames if "/scene/" in f.url)
            page.wait_for_function("document.querySelector('#sv-player .sp-time').textContent.startsWith('1.50')")
            assert abs(frame.evaluate("window.__timelines.intro.time()") - 1.5) < 1e-6

            page.click("#sv-player .seg button[data-v=box]")
            box = page.locator("#sv-player .sp-overlay").bounding_box()
            to_screen = lambda x, y: (box["x"] + x / 1280 * box["width"], box["y"] + y / 720 * box["height"])
            # At 1.5 s the box (and its label) has moved 450 px right: x 550 to 850, y 420 to 620.
            page.mouse.move(*to_screen(540, 410))
            page.mouse.down()
            page.mouse.move(*to_screen(620, 470), steps=4)
            page.mouse.move(*to_screen(700, 520), steps=4)
            page.mouse.up()
            page.wait_for_function("document.querySelector('#sv-player .sp-ids').textContent.startsWith('Elements:')")
            assert page.locator("#sv-player .sp-ids").inner_text() == "Elements: label, box"
            page.fill("#sv-player .sp-text", "Make the label larger.")
            page.screenshot(path=str(out / "marked.png"))
            page.click("#sv-player .sp-send")
            page.wait_for_function("document.querySelector('#sv-player .sp-status').textContent === 'Sent to Claude'",
                                   timeout=30_000)

            req = next(e["request"] for e in emitted if e.get("type") == "request")
            assert req["action"] == "mark-scene" and req["scene"] == "intro" and req["version"] == 1
            assert req["t"] == 1.5 and req["ids"] == ["label", "box"] and req["world"] is None
            rect = req["mark"]["rect"]
            assert abs(rect["x"] - 540) < 8 and abs(rect["y"] - 410) < 8, rect
            assert abs(rect["w"] - 160) < 8 and abs(rect["h"] - 110) < 8, rect
            still = Path(req["marked"])
            assert still == p / "comments" / "intro" / "v1-t1.50-1.png"
            image = Image.open(still).convert("RGB")
            assert image.size == (1280, 720)
            assert near(image.getpixel((100, 650)), BACKGROUND)
            assert near(image.getpixel((620, 410)), (0xE5, 0x38, 0x2F), tol=40), image.getpixel((620, 410))
            comments = json.loads((p / "comments" / "intro" / "comments.json").read_text())
            assert [(c["request"], c["state"], c["marked"]) for c in comments] == [(req["id"], "open", str(still))]

            page.wait_for_selector(f'#sv-player .sp-comment[data-req="{req["id"]}"] button')
            page.click(f'#sv-player .sp-comment[data-req="{req["id"]}"] button')
            page.wait_for_timeout(500)
            assert {"type": "stop", "id": req["id"]} in emitted

            # A newer page version with no render: the player opens it at the same time.
            v2 = p / "scenes" / "intro" / "v2"
            v2.mkdir()
            (v2 / "index.html").write_text((SCENE_HTML % {"id": "intro", "duration": DURATION})
                                           .replace("Scene check", "Second render"), encoding="utf-8")
            (v2 / "gsap.min.js").write_bytes(GSAP.read_bytes())
            studio.poll()
            page.wait_for_function("document.querySelector('#sv-player h2').textContent.includes('v2')",
                                   timeout=30_000)
            page.wait_for_selector("#sv-player .sp-overlay.on", timeout=30_000)
            frame = next(f for f in page.frames if "/scenes/intro/v2/" in f.url)
            page.wait_for_function("document.querySelector('#sv-player .sp-time').textContent.startsWith('1.50')")
            assert frame.evaluate("document.getElementById('title').textContent") == "Second render"
            assert abs(frame.evaluate("window.__timelines.intro.time()") - 1.5) < 1e-6
            page.screenshot(path=str(out / "reloaded.png"))

            # On the page-only version, Send sends no still; the agent makes it with `stills`.
            page.click("#sv-player .seg button[data-v=point]")
            box = page.locator("#sv-player .sp-overlay").bounding_box()
            page.mouse.click(box["x"] + 640 / 1280 * box["width"], box["y"] + 200 / 720 * box["height"])
            page.wait_for_function("!document.querySelector('#sv-player .sp-ids').textContent.startsWith('Finding')")
            page.fill("#sv-player .sp-text", "Move the title down.")
            page.click("#sv-player .sp-send")
            page.wait_for_function("document.querySelector('#sv-player .sp-status').textContent === 'Sent to Claude'",
                                   timeout=30_000)
            second = [e["request"] for e in emitted if e.get("type") == "request"][-1]
            assert second["version"] == 2 and second["marked"] is None and second["t"] == 1.5
            assert "title" in second["ids"], second["ids"]
            assert not list((p / "comments" / "intro").glob("v2-*.png"))
            assert errors == []
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
