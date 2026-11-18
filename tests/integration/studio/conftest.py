"""One Playwright and one Chromium (the one HyperFrames renders scenes with) for the session; each test gets a new
browser context and page, so localStorage and cookies stay isolated between tests."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from tests.integration.studio.test_scene_player_page import HYPERFRAMES, chrome
from tests.prereq import require

VIEWPORT = {"width": 1500, "height": 1000}


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """Chromium launched once for the session, closed with its Playwright at the end."""
    require(HYPERFRAMES.is_file(), f"hyperframes in {HYPERFRAMES.parent} (run short-video's setup)")
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome())
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    """A page in a new browser context of VIEWPORT, closed with its context after the test."""
    context = browser.new_context(viewport=VIEWPORT)
    try:
        yield context.new_page()
    finally:
        context.close()
