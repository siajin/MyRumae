"""Collect the user's enrolled courses from the sidebar dropdown."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from playwright.async_api import Page

from ..selectors import HOME

log = logging.getLogger(__name__)


@dataclass
class CourseDTO:
    moodle_course_id: int
    course_url: str
    course_name: str
    section_label: Optional[str]  # e.g. "(01)" trailing section number
    course_code: Optional[str]
    semester: Optional[str]


# Match titles like:
#   "C프로그래밍 (01)"
#   "C프로그래밍 (2026-10, 40121_01_U)"
_TITLE_RE_FULL = re.compile(r"^(?P<name>.+?)\s*\((?P<sem>\d{4}-\d{2}),\s*(?P<code>[\w_]+)\)\s*$")
_TITLE_RE_SHORT = re.compile(r"^(?P<name>.+?)\s*\((?P<section>\d{2,3})\)\s*$")


def _parse_title(title: str) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Return (course_name, semester, course_code, section_label)."""
    m = _TITLE_RE_FULL.match(title)
    if m:
        return m.group("name").strip(), m.group("sem"), m.group("code"), None
    m = _TITLE_RE_SHORT.match(title)
    if m:
        return m.group("name").strip(), None, None, m.group("section")
    return title.strip(), None, None, None


async def collect_courses(page: Page) -> List[CourseDTO]:
    # Sidebar dropdown is on every page; ensure it's present by going to /my/.
    if "uclass.uos.ac.kr" not in page.url:
        await page.goto(HOME.DASHBOARD_URL, wait_until="domcontentloaded")

    items = await page.locator(HOME.COURSE_ITEMS).all()
    out: List[CourseDTO] = []
    seen_ids: set[int] = set()

    for item in items:
        cid_str = await item.get_attribute("data-courseid")
        if not cid_str:
            continue
        try:
            cid = int(cid_str)
        except ValueError:
            continue
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        link = item.locator(HOME.COURSE_LINK).first
        title = (await link.get_attribute("title")) or ""
        href = (await link.get_attribute("href")) or f"https://uclass.uos.ac.kr/course/view.php?id={cid}"

        name, semester, code, section = _parse_title(title)
        out.append(
            CourseDTO(
                moodle_course_id=cid,
                course_url=href,
                course_name=name,
                section_label=section,
                course_code=code,
                semester=semester,
            )
        )

    log.info("collected %d courses", len(out))
    return out
