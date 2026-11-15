"""`still` and `stills`: frames of index.html at given times, with headless Chromium."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .browser import LAUNCH_ARGS, Browser
from .common import HAError
from .project import Project

READY_TIMEOUT_MS = 30_000
# Two animation frames after a seek, so the seeked frame is painted before the screenshot.
READY = ("() => Promise.race([window.HA_READY, new Promise((_, reject) => "
         f"setTimeout(() => reject(new Error('HA_READY timed out')), {READY_TIMEOUT_MS}))])")
PAINTED = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def still_name(t: float) -> str:
    """`t1.5.png`, `t0.png`: the default file name of the still at `t` seconds."""
    return f"t{t:g}.png"


class Renderer:
    """One headless Chromium page on the project's index.html, at stage size."""

    def __init__(self, project: Project, browser: Browser | None = None) -> None:
        self.project = project
        self.browser = browser or Browser()

    def render(self, times: list[float], outs: list[Path]) -> dict:
        """Screenshot the frame at each time to the matching path. The page loads once with ?still&t=<first>
        and seeks to each later time."""
        p = self.project
        if not p.index_html.is_file():
            raise HAError(f"{p.index_html} not found; run build")
        animation = p.load()
        for out in outs:
            out.parent.mkdir(parents=True, exist_ok=True)
        url = p.index_html.as_uri() + f"?still&t={times[0]:g}"
        page_errors: list[str] = []
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(executable_path=str(self.browser.executable()), args=LAUNCH_ARGS)
            except PlaywrightError as e:
                raise HAError(f"cannot start Chromium: {e}") from None
            try:
                page = browser.new_page(viewport={"width": animation.width, "height": animation.height},
                                        device_scale_factor=1)
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(url, wait_until="load")
                if not page.evaluate("() => !!window.HA_READY"):
                    raise HAError("index.html did not start the player: " + "; ".join(page_errors or ["no HA_READY"]))
                try:
                    state = page.evaluate(READY)
                except PlaywrightError as e:
                    raise HAError(f"the player did not get ready: {e}") from None
                errors = list(dict.fromkeys(page_errors + state["errors"]))
                if errors:
                    raise HAError("the page reported errors:\n" + "\n".join(errors))
                for i, (t, out) in enumerate(zip(times, outs)):
                    if i:
                        page.evaluate("t => HA.seek(t)", t)
                    page.evaluate(PAINTED)
                    page.screenshot(path=str(out))
                late = [e for e in page_errors if e not in errors]
                if late:
                    raise HAError("the page reported errors while seeking:\n" + "\n".join(late))
                warnings = state["warnings"]
            finally:
                browser.close()
        return {"pngs": [str(o) for o in outs], "warnings": warnings}
