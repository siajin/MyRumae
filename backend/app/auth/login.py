"""Login orchestration: state.json -> keyring creds -> manual fallback."""
from __future__ import annotations

import logging
from typing import Optional

from playwright.async_api import BrowserContext, Page

from ..selectors import LOGIN
from . import credentials, session

log = logging.getLogger(__name__)


class LoginError(RuntimeError):
    pass


async def _login_with_credentials(page: Page, username: str, password: str) -> None:
    try:
        await page.goto(LOGIN.URL, wait_until="load", timeout=30_000)
    except Exception as e:
        # Navigation can be interrupted if UCLASS redirects us away from
        # /login/ because an SSO session already exists. That's a good sign;
        # let the caller's is_logged_in() probe confirm.
        log.info("login goto interrupted (likely SSO redirect): %s", e)
        return

    # If UCLASS redirected us off /login/ (already authenticated), skip the form.
    try:
        await page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass
    if "/login/" not in page.url:
        log.info("login page redirected to %s; skipping form fill", page.url)
        return

    await page.fill(LOGIN.USERNAME, username)
    await page.fill(LOGIN.PASSWORD, password)
    try:
        async with page.expect_navigation(wait_until="load", timeout=30_000):
            await page.click(LOGIN.SUBMIT)
    except Exception as e:
        log.info("login submit nav wait raised (likely chained redirect): %s", e)


async def ensure_logged_in(
    context: BrowserContext,
    page: Page,
    *,
    allow_manual: bool = True,
    prompt_credentials: Optional[callable] = None,
) -> None:
    """Best-effort login. Order: existing session -> keyring -> manual prompt.

    `prompt_credentials`: optional callable returning (username, password)
    when keyring is empty (e.g. console input in smoke scripts).
    """
    if await session.is_logged_in(page):
        log.info("session login OK")
        await session.save_state(context)
        return

    creds = credentials.load_credentials()
    if creds:
        username, password = creds
        log.info("attempting credential login for %s", username)
        try:
            await _login_with_credentials(page, username, password)
        except Exception as e:
            log.warning("credential login submit failed: %s", e)

        if await session.is_logged_in(page):
            await session.save_state(context)
            log.info("credential login OK")
            return

        log.warning("credential login did not produce a logged-in session")

    if not allow_manual:
        raise LoginError("session and credential login both failed")

    if prompt_credentials is None:
        raise LoginError(
            "no stored credentials and no prompt callback provided; "
            "run scripts/smoke_login.py first"
        )

    username, password = prompt_credentials()
    credentials.save_credentials(username, password)

    # Re-check before typing — an SSO redirect may have authenticated us
    # while the prompt was open.
    if await session.is_logged_in(page):
        await session.save_state(context)
        log.info("session became valid during prompt; skipping form")
        return

    log.info("attempting manual credential login")
    await _login_with_credentials(page, username, password)

    if not await session.is_logged_in(page):
        raise LoginError("manual login attempt failed; check ID/PW")

    await session.save_state(context)
    log.info("manual login OK; state saved")
