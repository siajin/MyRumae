"""Browser session state.json persistence and login probe."""
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from ..selectors import HOME

# backend/ root, resolved relative to this file so it works from any CWD.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = _BACKEND_ROOT / "playwright-state" / "state.json"


def state_exists() -> bool:
    return STATE_PATH.exists() and STATE_PATH.stat().st_size > 0


async def save_state(context: BrowserContext) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(STATE_PATH))


async def is_logged_in(page: Page) -> bool:
    """Probe by navigating to the dashboard and checking for the logout link.

    UCLASS may chain through SSO redirects, so we wait for the network to
    settle before judging. URL alone is unreliable: an unauthenticated user
    lands on /login/, but an authenticated SSO user can be bounced through
    /login/index.php → /course/view.php (default course).
    """
    try:
        await page.goto(HOME.DASHBOARD_URL, wait_until="load", timeout=30_000)
    except Exception:
        # treat any nav error as "unknown"; fall through to URL/DOM check
        pass

    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass

    if "/login/" in page.url:
        return False

    try:
        return await page.locator(HOME.LOGOUT_LINK).count() > 0
    except Exception:
        return False
