"""Collect assignment metadata (modtype_assign) and attachments."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from ..db import repository as repo
from ..downloader import paths as dl_paths
from ..downloader.download import download_via_click
from ..selectors import ASSIGN

log = logging.getLogger(__name__)


_DATE_RE = re.compile(
    r"(\d{4})\s*년?\s*[-./]?\s*(\d{1,2})\s*월?\s*[-./]?\s*(\d{1,2})"
    r"(?:\s*일)?(?:[\sT]+(\d{1,2}):(\d{2}))?"
)


def _parse_due(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 23
        mi = int(m.group(5)) if m.group(5) else 59
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


async def _due_at_from_table(page: Page) -> Optional[datetime]:
    """Find a row whose label cell mentions 마감/종료/Due, return parsed value."""
    labels = await page.locator(ASSIGN.DUE_AT_ROW_LABEL).all()
    for label in labels:
        try:
            text = (await label.inner_text()).strip()
        except Exception:
            continue
        if any(k in text for k in ("마감", "종료", "Due", "due")):
            value_loc = label.locator("xpath=following-sibling::td").first
            try:
                value = (await value_loc.inner_text()).strip()
            except Exception:
                continue
            return _parse_due(value)
    return None


async def collect_assignment(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    cmid: int,
    week: Optional[int] = None,
    source_label: Optional[str] = None,
) -> int:
    """Visit assignment page, upsert Assignment row, download attachments.
    Returns the number of newly downloaded attachments."""
    url = ASSIGN.URL_TMPL.format(cmid=cmid)
    await page.goto(url, wait_until="domcontentloaded")

    title_loc = page.locator(ASSIGN.TITLE).first
    title = None
    if await title_loc.count() > 0:
        title = (await title_loc.inner_text()).strip()

    desc_loc = page.locator(ASSIGN.DESCRIPTION).first
    description = None
    if await desc_loc.count() > 0:
        description = await desc_loc.inner_html()

    due_at = await _due_at_from_table(page)

    submitted_loc = page.locator(ASSIGN.SUBMITTED_FLAG).first
    submitted = await submitted_loc.count() > 0

    assignment = repo.upsert_assignment(
        db,
        course_id=course_id,
        cmid=cmid,
        title=title,
        due_at=due_at,
        description_html=description,
        url=page.url,
        submitted=submitted,
        source_label=source_label,
    )
    db.commit()

    new_files = 0
    attachments = await page.locator(ASSIGN.ATTACH).all()
    for att in attachments:
        att_href = await att.get_attribute("href") or ""

        fname = dl_paths.filename_from_url(att_href)
        if fname and repo.material_exists_by_filename(db, course_id, fname):
            log.info("assign cmid=%s: skip (filename dedupe) %s", cmid, fname)
            continue

        def _exists(sha: str) -> bool:
            return repo.material_exists_by_sha(db, course_id, sha)

        result = await download_via_click(
            page,
            att,
            course_name=course_name,
            source_label=source_label,
            sha_exists=_exists,
        )
        if result is None:
            continue

        repo.insert_material(
            db,
            course_id=course_id,
            source_type="assign_attach",
            cmid=cmid,
            week=week,
            source_label=source_label,
            assignment_id=assignment.id,
            title=result.suggested_filename,
            file_path=str(result.path),
            file_type=Path(result.suggested_filename).suffix.lstrip(".").lower() or "unknown",
            download_url=att_href,
            sha256=result.sha256,
            size_bytes=result.size_bytes,
        )
        db.commit()
        new_files += 1
        log.info("assign cmid=%s: downloaded %s", cmid, result.suggested_filename)

    return new_files
