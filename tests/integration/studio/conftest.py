"""One Playwright and one Chromium (the one HyperFrames renders scenes with) for the session; each test gets a new
browser context and page, so localStorage and cookies stay isolated between tests."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from tests.integration.studio.test_scene_player_page import HYPERFRAMES, chrome
from tests.prereq import require

VIEWPORT = {"width": 1500, "height": 1000}


@pytest.fixture(scope="package")
def browser() -> Iterator[Browser]:
    """Chromium launched once for the studio tests, closed with its Playwright after the last of them. Package
    scope, not session: the sync Playwright keeps an asyncio event loop running in the main thread while it is
    open, and a later test that calls `asyncio.run` fails under it."""
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
