"""Iterate course sections/activities and dispatch to per-modtype collectors."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page

from ..selectors import COURSE
from . import assignments, folders, ubboard

log = logging.getLogger(__name__)


_SECTION_ID_RE = re.compile(r"section-(\d+)")


@dataclass
class ActivityRef:
    cmid: int
    modtype: str
    section_idx: Optional[int]


def _modtype_from_class(class_str: str) -> Optional[str]:
    if not class_str:
        return None
    for token in class_str.split():
        if token.startswith("modtype_"):
            return token[len("modtype_") :]
    return None


async def _snapshot_activities(page: Page) -> list[ActivityRef]:
    """Read all activity metadata in one JS evaluation. Snapshotting avoids
    stale Locators after we navigate into individual activities."""
    raw = await page.evaluate(
        """() => {
            const out = [];
            const els = document.querySelectorAll('li.activity.activity-wrapper[data-id]');
            for (const el of els) {
                const cmid = el.getAttribute('data-id');
                const cls = el.className || '';
                const sec = el.closest('li.section, [id^="section-"]');
                let sectionId = null;
                if (sec) {
                    sectionId = sec.getAttribute('data-sectionid') || sec.id || null;
                }
                out.push({ cmid, cls, sectionId });
            }
            return out;
        }"""
    )
    refs: list[ActivityRef] = []
    for row in raw:
        try:
            cmid = int(row["cmid"])
        except (TypeError, ValueError):
            continue
        modtype = _modtype_from_class(row.get("cls") or "")
        if modtype is None:
            continue
        section_idx: Optional[int] = None
        sid = row.get("sectionId")
        if sid:
            if isinstance(sid, str) and sid.isdigit():
                section_idx = int(sid)
            elif isinstance(sid, str):
                m = _SECTION_ID_RE.search(sid)
                if m:
                    section_idx = int(m.group(1))
        refs.append(ActivityRef(cmid=cmid, modtype=modtype, section_idx=section_idx))
    return refs


async def collect_course_materials(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    moodle_course_id: int,
) -> dict:
    """Walk every activity in the course and collect by modtype.

    Returns counts for visibility.
    """
    url = COURSE.URL_FLAT.format(cid=moodle_course_id)
    await page.goto(url, wait_until="domcontentloaded")

    refs = await _snapshot_activities(page)
    log.info("course %s: %d activities", course_name, len(refs))

    counts = {"folder": 0, "ubboard": 0, "assign": 0, "skipped": 0, "downloaded": 0}

    for ref in refs:
        week: Optional[int] = ref.section_idx if ref.section_idx and ref.section_idx >= 1 else None
        try:
            if ref.modtype == "folder":
                downloaded = await folders.collect_folder_files(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                    week=week,
                )
                counts["folder"] += 1
                counts["downloaded"] += downloaded
            elif ref.modtype == "ubboard":
                downloaded = await ubboard.collect_board(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                )
                counts["ubboard"] += 1
                counts["downloaded"] += downloaded
            elif ref.modtype == "assign":
                downloaded = await assignments.collect_assignment(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                )
                counts["assign"] += 1
                counts["downloaded"] += downloaded
            else:
                counts["skipped"] += 1
        except Exception as e:
            log.exception("activity cmid=%s modtype=%s failed: %s", ref.cmid, ref.modtype, e)
            counts["skipped"] += 1

    return counts
