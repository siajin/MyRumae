"""Iterate course sections/activities and dispatch to per-modtype collectors."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page

from ..events import emit
from ..selectors import COURSE
from . import assignments, folders, ubboard, ubfile

log = logging.getLogger(__name__)


_SECTION_ID_RE = re.compile(r"section-(\d+)")


@dataclass
class ActivityRef:
    cmid: int
    modtype: str
    section_idx: Optional[int]
    title: Optional[str]


def _modtype_from_class(class_str: str) -> Optional[str]:
    if not class_str:
        return None
    for token in class_str.split():
        if token.startswith("modtype_"):
            return token[len("modtype_") :]
    return None


async def _snapshot_activities(page: Page) -> list[ActivityRef]:
    """Read all activity metadata in one JS evaluation. Snapshotting avoids
    stale Locators after we navigate into individual activities.

    Week detection:
      The outer `<li class="section">` carries `data-number="N"` — that is
      the authoritative week number. `id="section-N"` (DOM id) is the
      fallback. We never look at `data-sectionid` — that is a database
      id, not a week. And `closest()` is scoped to `li.section` (not the
      broader `[id^="section-"]`) so we don't accidentally land on the
      inner `<div id="section-item-{dbid}">` whose number is a DB id.
    """
    raw = await page.evaluate(
        """() => {
            const out = [];
            const els = document.querySelectorAll('li.activity.activity-wrapper[data-id]');
            for (const el of els) {
                const cmid = el.getAttribute('data-id');
                const cls = el.className || '';
                const sec = el.closest('li.section');
                let sectionNumber = null;
                let sectionDomId = null;
                if (sec) {
                    sectionNumber = sec.getAttribute('data-number');
                    sectionDomId = sec.id || null;
                }
                const attrSrc = el.querySelector('[data-activityname]');
                const titleAttr = attrSrc ? attrSrc.getAttribute('data-activityname') : '';
                // .instancename and div.activityname often include a hidden
                // screen-reader modtype suffix like <span class="accesshide"> 폴더</span>.
                // Clone the node, strip .accesshide children, then read text.
                let titleText = '';
                const nameEl = el.querySelector('div.activityname, .instancename, a.activity-container');
                if (nameEl) {
                    const clone = nameEl.cloneNode(true);
                    clone.querySelectorAll('.accesshide, .sr-only, .visually-hidden').forEach(n => n.remove());
                    titleText = (clone.textContent || '').replace(/\\s+/g, ' ').trim();
                }
                const title = (titleAttr || titleText || '').trim();
                out.push({ cmid, cls, sectionNumber, sectionDomId, title });
            }
            return out;
        }"""
    )

    def _parse_week(row: dict) -> Optional[int]:
        # Authoritative: data-number on the outer li.section.
        num = row.get("sectionNumber")
        if isinstance(num, str) and num.isdigit():
            return int(num)

        # Fallback: parse N from id="section-N" if data-number was missing.
        dom_id = row.get("sectionDomId")
        if isinstance(dom_id, str):
            m = _SECTION_ID_RE.search(dom_id)
            if m:
                return int(m.group(1))

        return None

    refs: list[ActivityRef] = []
    for row in raw:
        try:
            cmid = int(row["cmid"])
        except (TypeError, ValueError):
            continue
        modtype = _modtype_from_class(row.get("cls") or "")
        if modtype is None:
            continue
        section_idx = _parse_week(row)
        title = (row.get("title") or "").strip() or None
        refs.append(
            ActivityRef(
                cmid=cmid,
                modtype=modtype,
                section_idx=section_idx,
                title=title,
            )
        )
    return refs


def _source_label_for(ref: ActivityRef) -> str:
    """Folder name on disk.

    - Activity title (from data-activityname or .activityname text) is the
      core label.
    - When the activity lives inside a weekly section (section_idx >= 1),
      prefix with "<N>주차 (<title>)" so the folder makes the week visible.
    - Activities in the "general" section 0 (공지사항, 강의자료실 등) keep
      the title only — no 주차 prefix.
    """
    if ref.title:
        title = ref.title
    else:
        fallback = {
            "folder": "자료실",
            "ubboard": "게시판",
            "ubfile": "강의자료",
            "assign": "과제",
        }.get(ref.modtype, "기타")
        title = f"{fallback}_{ref.cmid}"

    if ref.section_idx and ref.section_idx >= 1:
        return f"{ref.section_idx}주차 ({title})"
    return title


async def collect_course_materials(
    page: Page,
    *,
    db,
    course_id: int,
    course_name: str,
    moodle_course_id: int,
) -> dict:
    """Walk every activity in the course and collect by modtype.

    After collection, batch-parse any pending materials for this course so
    the DOCX writer downstream sees populated ParsedContent rows.

    Returns counts for visibility.
    """
    url = COURSE.URL_FLAT.format(cid=moodle_course_id)
    await page.goto(url, wait_until="domcontentloaded")

    refs = await _snapshot_activities(page)
    log.info("course %s: %d activities", course_name, len(refs))

    counts = {
        "folder": 0,
        "ubboard": 0,
        "ubfile": 0,
        "assign": 0,
        "skipped": 0,
        "downloaded": 0,
        "parsed": 0,
        "parse_failed": 0,
        "parse_skipped": 0,
    }

    for ref in refs:
        week: Optional[int] = ref.section_idx if ref.section_idx and ref.section_idx >= 1 else None
        source_label = _source_label_for(ref)
        try:
            if ref.modtype == "folder":
                downloaded = await folders.collect_folder_files(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                    week=week,
                    source_label=source_label,
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
                    week=week,
                    source_label=source_label,
                )
                counts["ubboard"] += 1
                counts["downloaded"] += downloaded
            elif ref.modtype == "ubfile":
                downloaded = await ubfile.collect_ubfile(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                    week=week,
                    source_label=source_label,
                )
                counts["ubfile"] += 1
                counts["downloaded"] += downloaded
            elif ref.modtype == "assign":
                downloaded = await assignments.collect_assignment(
                    page,
                    db=db,
                    course_id=course_id,
                    course_name=course_name,
                    cmid=ref.cmid,
                    week=week,
                    source_label=source_label,
                )
                counts["assign"] += 1
                counts["downloaded"] += downloaded
            else:
                counts["skipped"] += 1
        except Exception as e:
            log.exception("activity cmid=%s modtype=%s failed: %s", ref.cmid, ref.modtype, e)
            counts["skipped"] += 1

    # ---- Batch-parse any pending/failed materials for this course --------
    # Import here to avoid a hard dep at module load time (keeps tests light).
    try:
        from ..db import repository as repo
        from ..parser.pipeline import parse_material

        pending = repo.materials_pending_parse(db, course_id=course_id)
        for m in pending:
            res = parse_material(db, m.id)
            status = res.get("status")
            if status == "done":
                counts["parsed"] += 1
            elif status == "skipped":
                counts["parse_skipped"] += 1
            else:
                counts["parse_failed"] += 1
    except Exception:
        log.exception("course %s: batch parse failed", course_name)

    emit(
        "course_done",
        course_id=course_id,
        course_name=course_name,
        downloaded=counts["downloaded"],
        parsed=counts["parsed"],
        skipped=counts["skipped"],
    )

    return counts
