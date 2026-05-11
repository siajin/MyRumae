"""End-to-end timetable refresh — called from `python -m app.cli timetable`
and from `scheduler.full_sync` at the end of every sync cycle.

Source = bundled master JSON (`backend/data/master/courses_2026_1.json`).
Applied to DB Courses by `course_code` or `course_name`.

Power-saving guard: a skip marker (`backend/data/user/.master_apply.json`)
records `(master_mtime, course_count)`. On entry, if both still match the
current state, the apply is skipped entirely — no JSON re-parse, no DB
writes. Touching the master file (e.g. via an app-store update) bumps
mtime and forces a reapply.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ..db import repository as repo
from ..db.models import Course
from ..events import emit
from . import catalog as tt_catalog
from . import courses_index

log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
MARKER_PATH = _BACKEND_ROOT / "data" / "user" / ".master_apply.json"


def _read_marker() -> dict:
    if not MARKER_PATH.exists():
        return {}
    try:
        return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.warning("master_apply marker unreadable; will reapply")
        return {}


def _write_marker(*, master_mtime: float, course_count: int) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "master_mtime": master_mtime,
        "course_count": course_count,
        "applied_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    MARKER_PATH.write_text(json.dumps(payload), encoding="utf-8")


async def refresh_timetable(*, allow_manual_login: bool = False) -> dict:
    """Apply the bundled master JSON to every Course in the DB.

    `allow_manual_login` is unused (kept for CLI-signature compat with the
    older browser-based path).
    """
    _ = allow_manual_login

    summary = {
        "courses": 0,
        "matched": 0,
        "unmatched": 0,
        "slots": 0,
        "professors_set": 0,
        "syllabus_weeks": 0,
        "skipped": False,
        "errors": 0,
    }

    master_path = courses_index.default_path()
    if not master_path.exists():
        emit(
            "master_missing",
            level="warn",
            path=str(master_path),
            message="bundled master JSON not found — was the app installed correctly?",
        )
        summary["errors"] = 1
        return summary

    try:
        master_mtime = master_path.stat().st_mtime
    except OSError:
        master_mtime = 0.0

    db = repo.session_scope()
    try:
        course_count = db.query(Course).count()

        marker = _read_marker()
        if (
            marker.get("master_mtime") == master_mtime
            and marker.get("course_count") == course_count
            and course_count > 0
        ):
            emit(
                "catalog_skipped",
                master_mtime=master_mtime,
                course_count=course_count,
                applied_at=marker.get("applied_at"),
            )
            summary["skipped"] = True
            summary["courses"] = course_count
            return summary

        load, apply_result = tt_catalog.apply_catalog_to_db(db)
    finally:
        db.close()

    emit(
        "catalog_loaded",
        entries=len(load.entries),
        path=str(load.path),
    )

    summary["courses"] = apply_result.total_courses
    summary["matched"] = apply_result.matched
    summary["unmatched"] = apply_result.unmatched
    summary["slots"] = apply_result.slots_upserted
    summary["professors_set"] = apply_result.professor_filled
    summary["syllabus_weeks"] = apply_result.syllabus_weeks_written

    for row in apply_result.per_course:
        emit(
            "catalog_apply",
            level="info" if row["matched_via"] != "none" else "warn",
            **row,
        )

    if load.exists and load.entries:
        _write_marker(
            master_mtime=master_mtime,
            course_count=apply_result.total_courses,
        )

    return summary
