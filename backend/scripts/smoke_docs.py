"""Generate DOCX summaries from data already in lms.db.

Deprecated: use `python -m app.cli regen-docx [--course N]` instead.
This wrapper is kept for back-compat with older docs/habits and will be
removed once Phase 2 ships.

Run from `backend/`:
    python scripts/smoke_docs.py                # all courses
    python scripts/smoke_docs.py --course 1     # one course by DB id

Renders Desktop/UOS_LMS_AI/<course>/<N>주차/정리/<N>주차_강의정리.docx for every
week with materials. Does NOT touch the LMS — purely a DB → filesystem step.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import repository as repo  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import Course  # noqa: E402
from app.docs.docx_writer import (  # noqa: E402
    generate_all,
    generate_course_summaries,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
log = logging.getLogger(__name__)


def main() -> None:
    log.warning("smoke_docs.py is deprecated; use 'python -m app.cli regen-docx'")
    init_db()

    ap = argparse.ArgumentParser()
    ap.add_argument("--course", type=int, default=None, help="DB course id (omit for all)")
    args = ap.parse_args()

    db = repo.session_scope()
    try:
        if args.course is None:
            counts = generate_all(db)
            print(f"\n결과: {counts}")
            return

        course = db.query(Course).get(args.course)
        if course is None:
            print(f"course id={args.course}: 찾을 수 없음")
            return
        written = generate_course_summaries(db, course=course)
        print(f"\n과목: {course.course_name}")
        print(f"생성된 DOCX: {len(written)}개")
        for p in written:
            print(f"  - {p}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
