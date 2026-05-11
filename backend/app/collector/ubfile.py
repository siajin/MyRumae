"""Collect a single-file UCLASS activity (modtype_ubfile).

ubfile is the UCLASS-specific "single file" upload — one PDF/PPT per
activity, typically used for weekly lecture materials. The view page may:

  (a) auto-trigger a browser download (Content-Disposition: attachment), or
  (b) render a single `<a href=".../pluginfile.php/...">` the user clicks.

We try (a) first by wrapping `page.goto(URL)` in `expect_download`, then
fall back to (b) by scanning for pluginfile links.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeout

from ..db import repository as repo
from ..downloader import paths
from ..downloader.download import DownloadedFile, download_via_click
from ..selectors import UBFILE

log = logging.getLogger(__name__)


def _file_type_from_name(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".") or "unknown"


async def _try_auto_download(
    page: Page,
    *,
    url: str,
    course_name: str,
    source_label: Optional[str],
    sha_exists,
    timeout_ms: int = 30_000,
) -> Optional[DownloadedFile]:
    """If the ubfile page auto-downloads, capture it via expect_download.
    Returns None if the page renders normally (no download fired)."""
    paths.ensure_dirs()
    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                pass
            download = await dl_info.value
    except PWTimeout:
        return None
    except Exception as e:
        log.warning("ubfile auto-download probe failed: %s", e)
        return None

    suggested = download.suggested_filename or "ubfile.bin"
    tmp = paths.TEMP_ROOT / suggested
    idx = 0
    while tmp.exists():
        idx += 1
        tmp = paths.TEMP_ROOT / f"{idx}_{suggested}"
    try:
        await download.save_as(str(tmp))
    except Exception as e:
        log.warning("ubfile save_as failed: %s", e)
        return None

    # Reuse the dedupe + move helper inside download.py path conventions.
    import hashlib
    import shutil

    h = hashlib.sha256()
    with tmp.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    sha = h.hexdigest()
    if sha_exists(sha):
        tmp.unlink(missing_ok=True)
        log.info("ubfile dedupe: %s already in DB", suggested)
        return None

    final = paths.original_path(course_name, source_label, suggested)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        final.unlink()
    shutil.move(str(tmp), str(final))
    return DownloadedFile(
        path=final,
        sha256=sha,
        size_bytes=final.stat().st_size,
        suggested_filename=suggested,
    )


async def collect_ubfile(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    cmid: int,
    week: Optional[int] = None,
    source_label: Optional[str] = None,
) -> int:
    """Download the single file behind this ubfile activity.

    Returns 1 on new download, 0 on dedupe / no file.
    """
    url = UBFILE.URL_TMPL.format(cmid=cmid)

    def _exists(sha: str) -> bool:
        return repo.material_exists_by_sha(db, course_id, sha)

    # Path A — page auto-downloads on navigate.
    result = await _try_auto_download(
        page,
        url=url,
        course_name=course_name,
        source_label=source_label,
        sha_exists=_exists,
    )

    # Path B — view page rendered, click the pluginfile link.
    if result is None:
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            log.warning("ubfile goto failed (cmid=%s): %s", cmid, e)
            return 0

        links = await page.locator(UBFILE.FILE_LINK).all()
        if not links:
            log.info("ubfile cmid=%s: no pluginfile links and no auto-download", cmid)
            return 0
        href = await links[0].get_attribute("href") or ""

        fname = paths.filename_from_url(href)
        if fname and repo.material_exists_by_filename(db, course_id, fname):
            log.info("ubfile cmid=%s: skip (filename dedupe) %s", cmid, fname)
            return 0

        result = await download_via_click(
            page,
            links[0],
            course_name=course_name,
            source_label=source_label,
            sha_exists=_exists,
        )
        if result is None:
            return 0

        title = result.suggested_filename
        repo.insert_material(
            db,
            course_id=course_id,
            source_type="ubfile",
            cmid=cmid,
            week=week,
            source_label=source_label,
            title=title,
            file_path=str(result.path),
            file_type=_file_type_from_name(title),
            download_url=href,
            sha256=result.sha256,
            size_bytes=result.size_bytes,
        )
        db.commit()
        log.info("ubfile cmid=%s: downloaded %s (link)", cmid, title)
        return 1

    # Path A succeeded — persist Material.
    title = result.suggested_filename
    repo.insert_material(
        db,
        course_id=course_id,
        source_type="ubfile",
        cmid=cmid,
        week=week,
        source_label=source_label,
        title=title,
        file_path=str(result.path),
        file_type=_file_type_from_name(title),
        download_url=url,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
    )
    db.commit()
    log.info("ubfile cmid=%s: downloaded %s (auto)", cmid, title)
    return 1
