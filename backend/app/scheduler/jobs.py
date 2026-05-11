"""Full-sync orchestration and APScheduler integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..auth import login as auth_login
from ..collector import courses as collect_courses_mod
from ..collector.browser import browser_session
from ..collector.course_page import collect_course_materials
from ..db import repository as repo
from ..events import emit

log = logging.getLogger(__name__)

_sync_lock = asyncio.Lock()


async def full_sync(*, allow_manual_login: bool = False) -> dict:
    """Run a complete sync cycle. Returns summary counts.

    Concurrency-guarded: overlapping schedules wait on the lock.
    """
    async with _sync_lock:
        log.info("full_sync starting")
        summary = {"courses": 0, "downloaded": 0, "errors": 0}

        async with browser_session() as (context, page):
            emit("login_started")
            try:
                await auth_login.ensure_logged_in(
                    context, page, allow_manual=allow_manual_login
                )
                emit("login_ok")
            except auth_login.LoginError as e:
                log.error("login failed: %s", e)
                summary["errors"] += 1
                emit("login_failed", level="error", reason=str(e))
                return summary

            course_dtos = await collect_courses_mod.collect_courses(page)
            summary["courses"] = len(course_dtos)
            emit("course_listed", count=len(course_dtos))

            db = repo.session_scope()
            try:
                for idx, dto in enumerate(course_dtos):
                    course = repo.upsert_course(
                        db,
                        moodle_course_id=dto.moodle_course_id,
                        course_url=dto.course_url,
                        course_name=dto.course_name,
                        semester=dto.semester,
                        course_code=dto.course_code,
                    )
                    db.commit()

                    course_name = dto.course_name or f"course_{dto.moodle_course_id}"
                    emit(
                        "course_started",
                        course_id=course.id,
                        course_name=course_name,
                        moodle_id=dto.moodle_course_id,
                        index=idx,
                        total=len(course_dtos),
                    )
                    try:
                        counts = await collect_course_materials(
                            page,
                            db=db,
                            course_id=course.id,
                            course_name=course_name,
                            moodle_course_id=dto.moodle_course_id,
                        )
                        summary["downloaded"] += counts["downloaded"]
                        log.info("course %s done: %s", course_name, counts)

                        # Generate user-friendly DOCX summaries (정리/) per week
                        try:
                            from ..docs.docx_writer import generate_course_summaries
                            written = generate_course_summaries(db, course=course)
                            log.info("course %s: %d summary docx written", course_name, len(written))
                            for p in written:
                                emit("docx_written", course_id=course.id, path=str(p))
                        except Exception:
                            log.exception("course %s: docx summary failed", course_name)
                    except Exception as e:
                        log.exception("course %s failed", course_name)
                        summary["errors"] += 1
                        emit(
                            "error",
                            level="error",
                            stage="course",
                            course_id=course.id,
                            course_name=course_name,
                            message=str(e),
                        )

                    repo.mark_course_synced(db, course.id)
                    db.commit()
            finally:
                db.close()

            # Enrich Course rows from the bundled master JSON (timetable
            # slots, professor, weekly topics). Skip-marker keeps this near
            # zero-cost when nothing changed since last sync.
            try:
                from ..timetable import refresh_timetable
                tt_summary = await refresh_timetable(allow_manual_login=False)
                if tt_summary.get("errors"):
                    summary["errors"] += tt_summary["errors"]
            except Exception:
                log.exception("timetable refresh failed")
                summary["errors"] += 1

            # refresh state.json after a successful pass
            try:
                from ..auth import session as session_mod
                await session_mod.save_state(context)
            except Exception:
                log.exception("state.json refresh failed")

        log.info("full_sync done: %s", summary)
        return summary


_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler(interval_minutes: int = 30) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = AsyncIOScheduler()
    sched.add_job(
        full_sync,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="lms_full_sync",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    log.info("scheduler started (every %d minutes)", interval_minutes)
    return sched
