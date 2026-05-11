"""Smoke test for Phase 1.5: bundled master JSON -> DB enrichment.

No LMS login. No browser. Reads the bundled
`backend/data/master/courses_2026_1.json`, matches every entry against DB
Course rows by course_code / course_name, and upserts timetable_slots +
syllabus rows.

JSON Lines emission is suppressed (MYRUMAE_EVENTS=off) — output is for
humans only.

Examples (run from `backend/`):

    # Show master + DB courses + match plan (no writes)
    python scripts\\smoke_timetable.py --dry-run

    # Apply
    python scripts\\smoke_timetable.py

Recommended first run:
  1) python -m app.cli sync             (populate Course rows)
  2) python scripts\\smoke_timetable.py  (verify auto-apply works)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("MYRUMAE_EVENTS", "off")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import repository as repo  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import Course, Timetable  # noqa: E402
from app.timetable import catalog as tt_catalog  # noqa: E402
from app.timetable import courses_index  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

_WEEKDAYS_KO = ("월", "화", "수", "목", "금", "토", "일")


def _wd(n: int) -> str:
    return _WEEKDAYS_KO[n] if 0 <= n < 7 else f"?{n}"


def _print_master(load: tt_catalog.CatalogLoadResult) -> None:
    print(f"\n=== Master ({load.path}) ===")
    print(f"  exists: {load.exists}")
    print(f"  entries: {len(load.entries)}")
    for err in load.parse_errors:
        print(f"  [parse-error] {err}")


def _print_db_courses(courses: list[Course]) -> None:
    print(f"\n=== DB Courses ({len(courses)}개) ===")
    for c in courses:
        print(f"  id={c.id:>3}  name={c.course_name!r}  code={c.course_code!r}  sem={c.semester!r}")


def _print_matches(courses: list[Course], entries: list[tt_catalog.CatalogEntry]) -> None:
    print("\n=== Matching plan ===")
    for c in courses:
        m = tt_catalog.match_course(entries, c)
        if m.entry is None:
            print(f"  - {c.course_name!r}  (code={c.course_code!r})  -> NO MATCH")
            continue
        slot_str = ", ".join(
            f"{_wd(s.weekday)} {s.start_time}-{s.end_time}" for s in m.entry.slots
        ) or "(no slots)"
        print(f"  - {c.course_name!r}  (code={c.course_code!r})"
              f"  -> via={m.via}, professor={m.entry.professor!r}, {slot_str}")


def _print_apply(apply_result: tt_catalog.ApplyResult) -> None:
    print("\n=== Apply result ===")
    print(f"  total_courses           = {apply_result.total_courses}")
    print(f"  matched                 = {apply_result.matched}")
    print(f"  unmatched               = {apply_result.unmatched}")
    print(f"  slots_upserted          = {apply_result.slots_upserted}")
    print(f"  professor_filled        = {apply_result.professor_filled}")
    print(f"  syllabus_weeks_written  = {apply_result.syllabus_weeks_written}")


def _print_db_slots(db, courses: list[Course]) -> None:
    print("\n=== DB Timetable slots (now) ===")
    for c in courses:
        slots = db.query(Timetable).filter(Timetable.course_id == c.id).order_by(
            Timetable.weekday.asc(), Timetable.start_time.asc()
        ).all()
        if not slots:
            print(f"  {c.course_name!r}: (none)")
            continue
        print(f"  {c.course_name!r}:")
        for s in slots:
            print(f"    {_wd(s.weekday)} {s.start_time}-{s.end_time}  loc={s.location!r}  src={s.source}")


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 1.5 timetable smoke (master JSON -> DB)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show master + matches but do not write to DB",
    )
    args = p.parse_args()

    init_db()

    master_path = courses_index.default_path()
    if not master_path.exists():
        print(f"\nERROR: 마스터 JSON 이 없습니다.\n  파일: {master_path}\n"
              f"  앱 설치/번들이 올바른지 확인하세요.")
        return 1

    load = tt_catalog.load_unified_as_catalog()
    _print_master(load)

    db = repo.session_scope()
    try:
        courses = db.query(Course).order_by(Course.id.asc()).all()
        _print_db_courses(courses)

        if not courses:
            print("\nDB Course 가 비어있습니다. 먼저 `python -m app.cli sync` 한 번 돌리세요.")
            return 1

        if args.dry_run:
            _print_matches(courses, load.entries)
            print("\n--dry-run 이므로 DB 쓰기는 건너뜁니다.")
            return 0

        _, apply_result = tt_catalog.apply_catalog_to_db(db)
        _print_apply(apply_result)
        _print_db_slots(db, courses)
        print("\n=== 끝 ===")
        return 0 if apply_result.matched > 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
