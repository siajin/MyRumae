"""Async Playwright browser/context manager."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..auth import session

log = logging.getLogger(__name__)


def _headless_default() -> bool:
    val = os.environ.get("UCLASS_HEADLESS", "1")
    return val not in ("0", "false", "False")


@asynccontextmanager
async def browser_session(*, headless: bool | None = None):
    """Yield (context, page) ready for use. Loads state.json if present.

    Always closes the browser cleanly on exit.
    """
    headless = _headless_default() if headless is None else headless
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=headless)
        try:
            ctx_kwargs: dict = {"accept_downloads": True}
            if session.state_exists():
                ctx_kwargs["storage_state"] = str(session.STATE_PATH)

            context: BrowserContext = await browser.new_context(**ctx_kwargs)
            page: Page = await context.new_page()
            try:
                yield context, page
            finally:
                await context.close()
        finally:
            await browser.close()
