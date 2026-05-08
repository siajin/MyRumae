"""Smoke test: collect courses, optionally walk one course's materials.

Run from `backend/`:
    python scripts/smoke_collect.py --course-index 0 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import login as auth_login  # noqa: E402
from app.collector.browser import browser_session  # noqa: E402
from app.collector.course_page import collect_course_materials, _snapshot_activities  # noqa: E402
from app.collector.courses import collect_courses  # noqa: E402
from app.db import repository as repo  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.selectors import COURSE  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


async def _run(course_index: int, dry_run: bool) -> None:
    init_db()

    async with browser_session() as (context, page):
        await auth_login.ensure_logged_in(context, page, allow_manual=False)

        course_dtos = await collect_courses(page)
        print(f"\n=== 과목 {len(course_dtos)}개 ===")
        for i, c in enumerate(course_dtos):
            print(f"  [{i}] {c.course_name} | code={c.course_code} | sem={c.semester} | id={c.moodle_course_id}")

        if course_index < 0 or course_index >= len(course_dtos):
            print("course_index out of range; nothing else to do.")
            return

        target = course_dtos[course_index]
        print(f"\n=== 과목 {course_index} 활동 스냅샷 (dry-run={dry_run}) ===")
        await page.goto(COURSE.URL_FLAT.format(cid=target.moodle_course_id), wait_until="domcontentloaded")
        refs = await _snapshot_activities(page)
        for r in refs:
            print(f"  cmid={r.cmid:<6} modtype={r.modtype:<10} section={r.section_idx}")

        if dry_run:
            return

        # Real run for one course
        db = repo.session_scope()
        try:
            course = repo.upsert_course(
                db,
                moodle_course_id=target.moodle_course_id,
                course_url=target.course_url,
                course_name=target.course_name,
                semester=target.semester,
                course_code=target.course_code,
            )
            db.commit()
            counts = await collect_course_materials(
                page,
                db=db,
                course_id=course.id,
                course_name=target.course_name or f"course_{target.moodle_course_id}",
                moodle_course_id=target.moodle_course_id,
            )
            print(f"\n결과: {counts}")
        finally:
            db.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--course-index", type=int, default=0, help="0-based index into course list")
    p.add_argument("--dry-run", action="store_true", help="Only list activities; no downloads")
    args = p.parse_args()
    asyncio.run(_run(args.course_index, args.dry_run))


if __name__ == "__main__":
    main()
