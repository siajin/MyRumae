"""Playwright-based file downloads with sha256 dedupe."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import Locator, Page, TimeoutError as PWTimeout

from . import paths

log = logging.getLogger(__name__)

_concurrency = asyncio.Semaphore(2)


@dataclass
class DownloadedFile:
    path: Path
    sha256: str
    size_bytes: int
    suggested_filename: str


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def download_via_click(
    page: Page,
    locator: Locator,
    *,
    course_name: str,
    source_label: Optional[str],
    sha_exists: callable,  # (sha256) -> bool
    timeout_ms: int = 60_000,
) -> Optional[DownloadedFile]:
    """Click `locator` to trigger a download, stage into data/temp, then move
    into Desktop/UOS_LMS_AI/<course>/<source_label>/원본/ if not a duplicate.
    Returns None on duplicate or failure."""
    paths.ensure_dirs()

    async with _concurrency:
        try:
            async with page.expect_download(timeout=timeout_ms) as dl_info:
                await locator.click()
            download = await dl_info.value
        except PWTimeout:
            log.warning("download timeout")
            return None
        except Exception as e:
            log.warning("download click failed: %s", e)
            return None

        suggested = download.suggested_filename or "download.bin"
        tmp = paths.TEMP_ROOT / suggested
        # collision-safe temp name
        idx = 0
        while tmp.exists():
            idx += 1
            tmp = paths.TEMP_ROOT / f"{idx}_{suggested}"

        try:
            await download.save_as(str(tmp))
        except Exception as e:
            log.warning("download save_as failed: %s", e)
            return None

        sha = _sha256_file(tmp)
        if sha_exists(sha):
            log.info("dedupe: %s already in DB", suggested)
            tmp.unlink(missing_ok=True)
            return None

        final = paths.original_path(course_name, source_label, suggested)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            final.unlink()
        # shutil.move handles cross-volume moves (temp → Desktop) where
        # Path.rename can fail on Windows.
        shutil.move(str(tmp), str(final))

        return DownloadedFile(
            path=final,
            sha256=sha,
            size_bytes=final.stat().st_size,
            suggested_filename=suggested,
        )
