"""Collect notice/board (modtype_ubboard) articles and their attachments."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page

from ..db import repository as repo
from ..downloader.download import download_via_click
from ..selectors import BOARD

log = logging.getLogger(__name__)


def _parse_bwid(href: str) -> Optional[int]:
    try:
        q = parse_qs(urlparse(href).query)
        if "bwid" in q:
            return int(q["bwid"][0])
    except (ValueError, KeyError):
        pass
    return None


async def _safe_inner_text(page: Page, selector: str) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return None
        return (await loc.inner_text()).strip()
    except Exception:
        return None


async def _safe_inner_html(page: Page, selector: str) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return None
        return await loc.inner_html()
    except Exception:
        return None


_DATE_RE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")


def _parse_posted_at(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h = int(m.group(4)) if m.group(4) else 0
    mi = int(m.group(5)) if m.group(5) else 0
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


async def collect_board(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    cmid: int,
) -> int:
    """Visit the board's article list, then each article. Returns total new
    material count (article attachments)."""
    url = BOARD.URL_TMPL.format(cmid=cmid)
    await page.goto(url, wait_until="domcontentloaded")

    article_links = await page.locator(BOARD.ARTICLE_LINK).all()
    article_hrefs: list[str] = []
    for link in article_links:
        href = await link.get_attribute("href")
        if href and "bwid=" in href:
            article_hrefs.append(href)

    # Dedupe href list (the page often has multiple buttons per article)
    seen_bwids: set[int] = set()
    new_files = 0

    for href in article_hrefs:
        bwid = _parse_bwid(href)
        if bwid is None or bwid in seen_bwids:
            continue
        seen_bwids.add(bwid)

        try:
            await page.goto(href, wait_until="domcontentloaded")
        except Exception as e:
            log.warning("article goto failed (bwid=%s): %s", bwid, e)
            continue

        title = await _safe_inner_text(page, BOARD.ARTICLE_TITLE)
        author = await _safe_inner_text(page, BOARD.ARTICLE_AUTHOR)
        posted_raw = await _safe_inner_text(page, BOARD.ARTICLE_POSTED_AT)
        body = await _safe_inner_html(page, BOARD.ARTICLE_BODY)

        repo.upsert_notice(
            db,
            course_id=course_id,
            cmid=cmid,
            bwid=bwid,
            title=title,
            author=author,
            posted_at=_parse_posted_at(posted_raw),
            body_html=body,
            url=page.url,
        )
        db.commit()

        attachments = await page.locator(BOARD.ARTICLE_ATTACH).all()
        for att in attachments:
            att_href = await att.get_attribute("href") or ""

            def _exists(sha: str) -> bool:
                return repo.material_exists_by_sha(db, course_id, sha)

            result = await download_via_click(
                page,
                att,
                course_name=course_name,
                week=None,
                sha_exists=_exists,
            )
            if result is None:
                continue

            repo.insert_material(
                db,
                course_id=course_id,
                source_type="ubboard_attach",
                cmid=cmid,
                week=None,
                post_id=bwid,
                title=result.suggested_filename,
                file_path=str(result.path),
                file_type=Path(result.suggested_filename).suffix.lstrip(".").lower() or "unknown",
                download_url=att_href,
                sha256=result.sha256,
                size_bytes=result.size_bytes,
            )
            db.commit()
            new_files += 1
            log.info("ubboard cmid=%s bwid=%s: downloaded %s", cmid, bwid, result.suggested_filename)

    return new_files
