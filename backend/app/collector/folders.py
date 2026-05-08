"""Collect files from a Moodle folder activity (modtype_folder)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from ..db import repository as repo
from ..downloader.download import DownloadedFile, download_via_click
from ..selectors import FOLDER

log = logging.getLogger(__name__)


def _file_type_from_name(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".") or "unknown"


async def collect_folder_files(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    cmid: int,
    week: Optional[int],
) -> int:
    """Return count of newly downloaded materials."""
    url = FOLDER.URL_TMPL.format(cmid=cmid)
    await page.goto(url, wait_until="domcontentloaded")

    links = await page.locator(FOLDER.FILE_LINK).all()
    if not links:
        log.info("folder cmid=%s: no pluginfile links", cmid)
        return 0

    new_count = 0
    for link in links:
        href = await link.get_attribute("href") or ""

        def _exists(sha: str) -> bool:
            return repo.material_exists_by_sha(db, course_id, sha)

        result: Optional[DownloadedFile] = await download_via_click(
            page,
            link,
            course_name=course_name,
            week=week,
            sha_exists=_exists,
        )
        if result is None:
            continue

        title = result.suggested_filename
        repo.insert_material(
            db,
            course_id=course_id,
            source_type="folder",
            cmid=cmid,
            week=week,
            title=title,
            file_path=str(result.path),
            file_type=_file_type_from_name(title),
            download_url=href,
            sha256=result.sha256,
            size_bytes=result.size_bytes,
        )
        db.commit()
        new_count += 1
        log.info("folder cmid=%s: downloaded %s", cmid, title)

    return new_count
