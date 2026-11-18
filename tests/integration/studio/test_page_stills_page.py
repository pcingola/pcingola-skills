"""The Studio page in headless Chromium on a short-video project whose key scene is drawn in its page: the style step
shows the three stills of its page as the samples, with their page style and "Use this style"; once a style is
chosen, the storyboard card shows the scene's newest still instead of the "Drawn scene" placeholder, and the scene
view shows it in step 1 with a change (Send) and without variations or other styles. Behaviour: plugins/studio/skills/
videos/SKILL.md, sections Page stills and Page style."""
from __future__ import annotations

import json
import threading

from studio_server.server import Heartbeat, Studio

from tests.integration.studio.test_scene_player_page import HYPERFRAMES
from tests.prereq import requires
from tests.unit.studio.conftest import png
from tests.unit.studio.test_page_stills import DRAWN, still
from tests.unit.studio.test_video import make_video

BOARD = {"title": "Cases", "topic": "Cases over time.",
         "scenes": [DRAWN, {"id": "close", "brief": "The total counts up.", "narration": ["That is all."],
                            "beats": ["total"]}]}


@requires(HYPERFRAMES.is_file(), "hyperframes in short-video's node directory (run short-video's setup)")
def test_stills_in_style_step_and_storyboard(tmp_path, page):
    """Three style samples that are stills of the drawn key scene's page show as sample cards with their page
    style; after the samples are gone (a style chosen), the storyboard row of the drawn scene shows its newest
    still, the storyboard step stays open and not done until every drawn scene has a still, and its scene view shows "Still of the page" with Send and without "3 variations"; "Use this still" shows on a still of an older page only and sends a use-still request."""
    emitted: list[dict] = []
    studio = Studio(tmp_path / "Studio", emit=emitted.append, heartbeat=Heartbeat(600.0))
    p = make_video(studio.root, storyboard=BOARD, pictures={},
                   meta={"style": None, "samples": {"scene": "chart", "versions": [1, 2, 3], "style": "auto"}})
    for n in (1, 2, 3):
        still(p, n, f"scenes/chart/v{n}", data=png(16, 9))
    httpd = studio.serve()
    threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True).start()
    studio.poll()
    try:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script("localStorage.setItem('studio-kind', 'short-video')")
        page.goto(studio.url)
        page.click("#projects button.project")
        page.wait_for_selector(".samples .sample img", state="attached")
        assert page.locator(".samples .sample img").count() == 3
        card = page.locator(".samples .sample").first.inner_text()
        assert "2D · flat · Inter · static" in card and "Use this style" in card
        assert "still of scene 1's page" in page.locator(".sampling").inner_text()

        meta = json.loads((p / "project.json").read_text())
        meta.pop("samples")
        meta["style"] = {"name": "ink"}
        (p / "project.json").write_text(json.dumps(meta))
        still(p, 4, "scenes/chart/v4", name="at_002.000.png", data=png(16, 9))
        (p / "scenes" / "chart" / "v4" / "index.html").write_text("<html></html>")
        studio.poll()
        page.wait_for_function("""(() => { const img = document.querySelector('.srow[data-id="chart"] .thumb img');
            return !!img && decodeURIComponent(img.src).endsWith('scenes/chart/v4/stills/at_002.000.png'); })()""",
                               timeout=30_000)
        assert page.locator('.srow[data-id="close"] .noimg.drawn').count() == 1
        # A drawn scene without a still keeps the storyboard step open and not done, as a missing picture does.
        board = page.locator("#sv-board")
        assert "folded" not in (board.get_attribute("class") or "")
        assert page.locator("#sv-board > h2 > .num.done").count() == 0
        still(p, 1, "scenes/close/v1", scene="close", data=png(16, 9))
        studio.poll()
        page.wait_for_selector("#sv-board > h2 > .num.done", state="attached", timeout=30_000)
        page.wait_for_selector("#sv-board.folded", state="attached")

        page.evaluate("""document.querySelector('.srow[data-id="chart"] .what').click()""")
        page.wait_for_selector("text=Still of the page")
        page.wait_for_function("(document.getElementById('d-img').src || '').endsWith('at_002.000.png')")
        acts = page.locator("#d-acts").inner_text()
        assert "Send" in acts and "Use as reference" in acts
        assert "3 variations" not in acts and "Try other styles" not in acts
        assert "Use this still" not in acts  # v4's page is the scene's latest page

        # An older still offers "Use this still", which sends a use-still request for it.
        page.click(".ver:has(b:text-is('v1'))")
        page.wait_for_function("decodeURIComponent(document.getElementById('d-img').src || '').includes('scenes/chart/v1/')")
        page.click("#d-acts button:text-is('Use this still')")
        req = None
        for _ in range(100):
            req = next((e["request"] for e in emitted if e.get("type") == "request"), None)
            if req:
                break
            page.wait_for_timeout(50)
        assert req and (req["action"], req["scene"], req["version"]) == ("use-still", "chart", 1)
        assert errors == []
    finally:
        httpd.shutdown()
        httpd.server_close()


@requires(HYPERFRAMES.is_file(), "hyperframes in short-video's node directory (run short-video's setup)")
def test_earlier_style_samples(tmp_path, page):
    """With a second round of samples (v4 to v6) waiting, the style step shows the three samples and, under "Earlier
    style samples", the first round's stills (v1 to v3); "Use this style" on an earlier one sends use-style with its
    version. Guards choosing a style from an earlier round (studio:videos SKILL.md, use-style)."""
    emitted: list[dict] = []
    studio = Studio(tmp_path / "Studio", emit=emitted.append, heartbeat=Heartbeat(600.0))
    p = make_video(studio.root, storyboard=BOARD, pictures={},
                   meta={"style": None, "samples": {"scene": "chart", "versions": [4, 5, 6], "style": "invent"}})
    for n in range(1, 7):
        still(p, n, f"scenes/chart/v{n}", data=png(16, 9))
    httpd = studio.serve()
    threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True).start()
    studio.poll()
    try:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script("localStorage.setItem('studio-kind', 'short-video')")
        page.goto(studio.url)
        page.click("#projects button.project")
        page.wait_for_selector("text=Earlier style samples")
        assert page.locator(".samples").count() == 2
        assert page.locator(".samples").nth(0).locator(".sample").count() == 3
        assert page.locator(".samples").nth(1).locator(".sample").count() == 3
        page.locator(".samples").nth(1).locator(".sample").last.locator("button:text-is('Use this style')").click()
        req = None
        for _ in range(100):
            req = next((e["request"] for e in emitted if e.get("type") == "request"), None)
            if req:
                break
            page.wait_for_timeout(50)
        assert req and (req["action"], req["version"]) == ("use-style", 1)
        assert errors == []
    finally:
        httpd.shutdown()
        httpd.server_close()


@requires(HYPERFRAMES.is_file(), "hyperframes in short-video's node directory (run short-video's setup)")
def test_silent_film_switch(tmp_path, page):
    """Step 1 of a project without a storyboard has a "Silent film" switch; turning it on writes `silent` true to
    project.json's film and the voice step says the voice is not used. Guards the silent film setting
    (studio:videos SKILL.md, Scenes and settings.yaml)."""
    studio = Studio(tmp_path / "Studio", emit=lambda e: None, heartbeat=Heartbeat(600.0))
    p = make_video(studio.root, storyboard=None, pictures={})
    httpd = studio.serve()
    threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True).start()
    studio.poll()
    try:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script("localStorage.setItem('studio-kind', 'short-video')")
        page.goto(studio.url)
        page.click("#projects button.project")
        switch = page.locator("label.switch:has-text('Silent film')")
        switch.wait_for()
        switch.locator("span").first.click()
        for _ in range(100):
            if json.loads((p / "project.json").read_text())["film"].get("silent") is True:
                break
            page.wait_for_timeout(50)
        assert json.loads((p / "project.json").read_text())["film"]["silent"] is True
        page.wait_for_selector("text=not used: the film is silent", state="attached")
        assert errors == []
    finally:
        httpd.shutdown()
        httpd.server_close()
