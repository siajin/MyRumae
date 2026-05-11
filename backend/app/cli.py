"""User-facing CLI entry point. This is what the Tauri Rust shell spawns.

Subcommands:
  sync             — one full sync cycle (login → courses → materials → parse → DOCX)
  regen-docx       — rebuild DOCX summaries from DB only (no LMS access)
  parse            — re-parse one material (--material ID) or all pending (--all)
  timetable        — apply data/course_catalog.json (or merged courses_*.json) to DB
  status           — print a one-shot DB status snapshot

Contract:
  * stdout is reserved for JSON Lines events (see app.events)
  * stderr carries human-readable logs
  * exit code 0 on success, 1 on uncaught failure

Cooperative cancel: the worker watches stdin in a background task; writing
the literal line "cancel" triggers a graceful shutdown. SIGTERM is not
supported on Windows so we don't rely on it.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

from .db import repository as repo
from .db.init_db import init_db
from .events import emit


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


_cancel_event = asyncio.Event()


async def _watch_stdin_for_cancel() -> None:
    """Cooperative cancel: Tauri writes 'cancel\\n' to our stdin to stop us."""
    # On Windows, asyncio's ProactorEventLoop registers stdin with IOCP via
    # CreateIoCompletionPort. A pipe handed to us by Tauri/tokio is not opened
    # with FILE_FLAG_OVERLAPPED, so the registration fails ("WinError 6 — handle
    # is invalid") AFTER connect_read_pipe returns successfully — too late to
    # catch with a try/except around the setup call. Skip the asyncio path
    # entirely and go straight to the synchronous poller thread.
    if sys.platform == "win32":
        await _watch_stdin_threaded()
        return

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    try:
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    except Exception:
        await _watch_stdin_threaded()
        return
    while True:
        line = await reader.readline()
        if not line:
            return
        if line.decode("utf-8", errors="ignore").strip().lower() == "cancel":
            _cancel_event.set()
            return


async def _watch_stdin_threaded() -> None:
    loop = asyncio.get_running_loop()

    def _read():
        try:
            for line in sys.stdin:
                if line.strip().lower() == "cancel":
                    loop.call_soon_threadsafe(_cancel_event.set)
                    return
        except Exception:
            return

    await asyncio.get_running_loop().run_in_executor(None, _read)


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- sync ------------------------------------------------------------------

async def _cmd_sync(args: argparse.Namespace) -> int:
    from .scheduler.jobs import full_sync

    run_id = _new_run_id()
    started = time.monotonic()
    emit("run_started", run_id=run_id, kind="sync")

    # Cancel watcher runs alongside the sync.
    cancel_task = asyncio.create_task(_watch_stdin_for_cancel())
    sync_task = asyncio.create_task(full_sync(allow_manual_login=False))

    try:
        done, pending = await asyncio.wait(
            {sync_task, asyncio.create_task(_cancel_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if _cancel_event.is_set() and not sync_task.done():
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass
            emit(
                "run_done",
                run_id=run_id,
                cancelled=True,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return 0

        summary = await sync_task
        emit(
            "run_done",
            run_id=run_id,
            downloaded=summary.get("downloaded", 0),
            errors=summary.get("errors", 0),
            courses=summary.get("courses", 0),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return 0 if summary.get("errors", 0) == 0 else 1
    finally:
        cancel_task.cancel()


# ---- regen-docx ------------------------------------------------------------

def _cmd_regen_docx(args: argparse.Namespace) -> int:
    from .db.models import Course
    from .docs.docx_writer import generate_all, generate_course_summaries

    run_id = _new_run_id()
    started = time.monotonic()
    emit("run_started", run_id=run_id, kind="regen-docx")

    db = repo.session_scope()
    try:
        if args.course is not None:
            course = db.get(Course, args.course)
            if course is None:
                emit("error", level="error", stage="regen-docx", message=f"course id={args.course} not found")
                emit("run_done", run_id=run_id, errors=1, duration_ms=int((time.monotonic() - started) * 1000))
                return 1
            written = generate_course_summaries(db, course=course)
            for p in written:
                emit("docx_written", course_id=course.id, path=str(p))
            emit(
                "run_done",
                run_id=run_id,
                courses=1,
                docx_written=len(written),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return 0

        result = generate_all(db)
        emit(
            "run_done",
            run_id=run_id,
            courses=result.get("courses", 0),
            docx_written=result.get("docx_written", 0),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return 0
    finally:
        db.close()


# ---- parse -----------------------------------------------------------------

def _cmd_parse(args: argparse.Namespace) -> int:
    from .parser.pipeline import parse_material, reparse_course

    run_id = _new_run_id()
    started = time.monotonic()
    emit("run_started", run_id=run_id, kind="parse")

    db = repo.session_scope()
    try:
        if args.material is not None:
            res = parse_material(db, args.material)
            emit(
                "run_done",
                run_id=run_id,
                status=res.get("status"),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return 0 if res.get("status") in ("done", "skipped") else 1

        totals = reparse_course(db, course_id=args.course)
        emit(
            "run_done",
            run_id=run_id,
            done=totals.get("done", 0),
            failed=totals.get("failed", 0),
            skipped=totals.get("skipped", 0),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return 0
    finally:
        db.close()


# ---- timetable -------------------------------------------------------------

async def _cmd_timetable_async(args: argparse.Namespace) -> int:
    from .timetable import refresh_timetable

    run_id = _new_run_id()
    started = time.monotonic()
    emit("run_started", run_id=run_id, kind="timetable")
    summary = await refresh_timetable(allow_manual_login=False)
    emit(
        "run_done",
        run_id=run_id,
        courses=summary.get("courses", 0),
        slots=summary.get("slots", 0),
        topics=summary.get("topics", 0),
        pdfs=summary.get("pdfs", 0),
        errors=summary.get("errors", 0),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return 0 if summary.get("errors", 0) == 0 else 1


def _cmd_timetable(args: argparse.Namespace) -> int:
    return asyncio.run(_cmd_timetable_async(args))


# ---- reset-db --------------------------------------------------------------

def _cmd_reset_db(args: argparse.Namespace) -> int:
    """Reset DB + caches (optionally Desktop tree). Emits events for the UI.

    Delegates to scripts/reset_db.py functions so shell users and the Tauri
    worker share one source of truth. Login state (keyring + state.json) is
    untouched here — that's scripts/reset.py's job.
    """
    # scripts/ is added to sys.path so we can import reset_db without dragging
    # a third package layout into app/.
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import reset_db as _rdb  # type: ignore[import-not-found]

    run_id = _new_run_id()
    started = time.monotonic()
    emit("run_started", run_id=run_id, kind="reset-db")

    # Defensive: if any prior import path (e.g. via reset_db.reset_desktop_tree
    # importing app.downloader.paths, which itself avoids importing db) ever
    # ends up creating a DB engine, dispose its connections before unlink.
    try:
        from .db.database import engine  # noqa: PLC0415
        engine.dispose()
    except Exception:
        pass

    try:
        db_paths = _rdb.reset_db()
        cache_paths = _rdb.reset_caches()
        desk_path = _rdb.reset_desktop_tree() if args.files else None

        emit(
            "run_done",
            run_id=run_id,
            db_removed=len(db_paths),
            caches_removed=len(cache_paths),
            desktop_tree_removed=bool(desk_path),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return 0
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        emit("error", level="error", stage="reset-db", message=str(e), traceback=tb)
        emit(
            "run_done",
            run_id=run_id,
            errors=1,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return 1


# ---- status ----------------------------------------------------------------

def _cmd_status(args: argparse.Namespace) -> int:
    from .auth.session import STATE_PATH, state_exists
    from .db.models import Assignment, Course, Material, Notice, ParsedContent

    db = repo.session_scope()
    try:
        emit(
            "status",
            courses=db.query(Course).count(),
            materials=db.query(Material).count(),
            notices=db.query(Notice).count(),
            assignments=db.query(Assignment).count(),
            parsed=db.query(ParsedContent).count(),
            state_json=str(STATE_PATH),
            state_exists=state_exists(),
        )
        return 0
    finally:
        db.close()


# ---- argparse + dispatch ---------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.cli", description="MyRumae worker CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="Run one full sync cycle")

    p_regen = sub.add_parser("regen-docx", help="Rebuild DOCX summaries from DB only")
    p_regen.add_argument("--course", type=int, default=None, help="Course id (omit = all)")

    p_parse = sub.add_parser("parse", help="Parse materials (PDF text + OCR fallback)")
    p_parse.add_argument("--material", type=int, default=None, help="Material id (single)")
    p_parse.add_argument("--course", type=int, default=None, help="Course id (batch pending)")

    sub.add_parser("timetable", help="Apply course catalog / merged JSON to DB")

    p_reset = sub.add_parser("reset-db", help="Wipe DB + caches (preserves login)")
    p_reset.add_argument("--files", action="store_true", help="Also delete Desktop/UOS_LMS_AI tree")

    sub.add_parser("status", help="Print one-shot DB status snapshot")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    _configure_logging()

    parser = _build_parser()
    args = parser.parse_args(argv)

    # reset-db must NOT open the DB — that would lock lms.db/-wal/-shm and
    # make the very unlink we're about to perform fail with WinError 32.
    if args.cmd != "reset-db":
        init_db()

    try:
        if args.cmd == "sync":
            return asyncio.run(_cmd_sync(args))
        if args.cmd == "regen-docx":
            return _cmd_regen_docx(args)
        if args.cmd == "parse":
            return _cmd_parse(args)
        if args.cmd == "timetable":
            return _cmd_timetable(args)
        if args.cmd == "reset-db":
            return _cmd_reset_db(args)
        if args.cmd == "status":
            return _cmd_status(args)
    except KeyboardInterrupt:
        emit("error", level="warn", stage="cli", message="interrupted")
        return 130
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        emit("error", level="error", stage="cli", message=str(e), traceback=tb)
        logging.exception("cli crashed")
        return 1

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
