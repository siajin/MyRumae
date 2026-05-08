"""Smoke test (headed): 브라우저 창을 띄워서 로그인 흐름을 눈으로 확인.

SSO 흐름 디버깅, 캡차/2FA 통과, selector 검증용.

Run from `backend/`:
    python scripts/smoke_login_headed.py
"""
from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import credentials, login as auth_login, session  # noqa: E402
from app.collector.browser import browser_session  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


def _prompt() -> tuple[str, str]:
    print("UCLASS 아이디/비밀번호를 입력하세요. keyring에 저장됩니다.")
    user = input("아이디: ").strip()
    pw = getpass.getpass("비밀번호: ")
    return user, pw


async def _run() -> None:
    has_state = session.state_exists()
    has_creds = credentials.load_credentials() is not None
    print(f"[headed] state.json: {'있음' if has_state else '없음'}, keyring: {'있음' if has_creds else '없음'}")

    async with browser_session(headless=False) as (context, page):
        await auth_login.ensure_logged_in(
            context, page, allow_manual=True, prompt_credentials=_prompt
        )
        ok = await session.is_logged_in(page)
        print(f"is_logged_in: {ok}")
        print(f"page.url: {page.url}")
        print(f"state path: {session.STATE_PATH.resolve()}")


if __name__ == "__main__":
    asyncio.run(_run())
