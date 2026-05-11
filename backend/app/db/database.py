import logging
import shutil
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

log = logging.getLogger(__name__)

# backend/ root, resolved relative to this file so it works from any CWD.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_USER_DIR = _BACKEND_ROOT / "data" / "user"
_MASTER_DIR = _BACKEND_ROOT / "data" / "master"


def _migrate_legacy_layout() -> None:
    """One-shot move of pre-split files into the new master/user dirs.

    Cheap (only runs `exists()` checks) and idempotent: once files have
    been moved, subsequent runs hit only the four `.exists()` checks.
    """
    legacy_data = _BACKEND_ROOT / "data"
    moves = [
        (legacy_data / "lms.db",                _USER_DIR / "lms.db"),
        (legacy_data / "parsed",                _USER_DIR / "parsed"),
        (legacy_data / "temp",                  _USER_DIR / "temp"),
        (legacy_data / "raw",                   _USER_DIR / "raw"),
        (legacy_data / "courses_2026_1.json",   _MASTER_DIR / "courses_2026_1.json"),
    ]
    for src, dst in moves:
        if not src.exists() or dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            log.info("legacy migrate: %s -> %s", src, dst)
        except Exception:
            log.exception("legacy migrate failed for %s", src)


_USER_DIR.mkdir(parents=True, exist_ok=True)
_migrate_legacy_layout()

_DB_PATH = (_USER_DIR / "lms.db").as_posix()

DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)


# WAL mode is required so the Tauri Rust shell can read the DB while the
# Python worker is writing during a sync. NORMAL synchronous is fine for
# our consistency needs (the worker writes per-course, not per-row).
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
