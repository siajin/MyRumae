"""Unified-courses JSON loader (backend/data/courses_<year>_<half>.json).

This module is the offline counterpart to the (LMS scrape + WISE API)
network paths. The unified JSON is produced by
`scripts/merge_courses.py` from `all_courses_<year>_<half>.json`
(전체교과목.txt 추출) + `wise_responses_<year>-<term>.json` (WISE API).

Public API:
    load_unified() -> UnifiedDoc                 (caches in module state)
    find_by_course_code("40121_01_U") -> UnifiedCourse | None
    find_by_subject_dvcl("40121", "01") -> UnifiedCourse | None
    find_by_name("C프로그래밍", *, semester=...) -> UnifiedCourse | None

The course_code parser accepts the UCLASS title convention
"<subject_no>_<dvcl_no>[_<suffix>]" (suffix is ignored).

Period→time mapping for converting `slots[].periods` to start/end
times uses the UOS standard 50-minute periods starting at 09:00. Override
with `UOS_PERIOD_TIMES` env var (JSON dict) if your campus deviates.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
# Bundled, read-only master catalog shipped with the app.
DATA_DIR = _BACKEND_ROOT / "data" / "master"


# ---------------------------------------------------------------------------
# Schema dataclasses (read-only view over the merged JSON)

@dataclass
class WeekRow:
    week: int
    topic: Optional[str] = None
    method: Optional[str] = None
    assignment: Optional[str] = None
    goal: Optional[str] = None
    class_type: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: dict) -> "WeekRow":
        return cls(
            week=int(raw.get("week") or 0),
            topic=raw.get("topic"),
            method=raw.get("method"),
            assignment=raw.get("assignment"),
            goal=raw.get("goal"),
            class_type=raw.get("class_type"),
        )


@dataclass
class SyllabusInfo:
    professor: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    evaluation: Optional[str] = None
    class_type: Optional[str] = None
    goal: Optional[str] = None
    shyr: Optional[int] = None
    term_label: Optional[str] = None
    weeks: list[WeekRow] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Optional[dict]) -> Optional["SyllabusInfo"]:
        if not raw:
            return None
        return cls(
            professor=raw.get("professor"),
            email=raw.get("email"),
            phone=raw.get("phone"),
            department=raw.get("department"),
            evaluation=raw.get("evaluation"),
            class_type=raw.get("class_type"),
            goal=raw.get("goal"),
            shyr=raw.get("shyr"),
            term_label=raw.get("term_label"),
            weeks=[WeekRow.from_raw(w) for w in (raw.get("weeks") or [])],
        )


@dataclass
class ScheduleSlot:
    weekday: Optional[str]              # "월"/"화"/... (Korean) or None
    periods: list[int] = field(default_factory=list)
    room: Optional[str] = None


@dataclass
class UnifiedCourse:
    key: str                            # "<subject_no>_<dvcl_no>"
    subject_no: str
    dvcl_no: str
    subject_nm: Optional[str]
    grade: Optional[str]
    credit: Optional[int]
    course_type: Optional[str]
    schedule_raw: Optional[str]
    slots: list[ScheduleSlot] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    enrolled: Optional[int] = None
    capacity: Optional[int] = None
    syllabus: Optional[SyllabusInfo] = None
    raw: dict = field(default_factory=dict)


@dataclass
class UnifiedDoc:
    path: Path
    year: int
    term: int
    semester: str                       # "2026-10"
    courses: list[UnifiedCourse]
    by_key: dict[str, UnifiedCourse]
    by_name: dict[str, UnifiedCourse]    # exact subject_nm → first match


# ---------------------------------------------------------------------------
# Loader (module-cached)

_DEFAULT_PATH = DATA_DIR / "courses_2026_1.json"
_cache: dict[Path, UnifiedDoc] = {}
_cache_mtime: dict[Path, float] = {}


def default_path() -> Path:
    return _DEFAULT_PATH


def _slot_from_raw(raw: dict) -> ScheduleSlot:
    return ScheduleSlot(
        weekday=raw.get("weekday"),
        periods=[int(p) for p in (raw.get("periods") or []) if isinstance(p, int) or str(p).isdigit()],
        room=raw.get("room"),
    )


def _course_from_raw(raw: dict) -> UnifiedCourse:
    sched = raw.get("schedule") or {}
    enr = raw.get("enrollment") or {}
    return UnifiedCourse(
        key=raw.get("key") or f"{raw.get('subject_no','')}_{raw.get('dvcl_no','')}",
        subject_no=str(raw.get("subject_no") or "").strip(),
        dvcl_no=str(raw.get("dvcl_no") or "").strip(),
        subject_nm=raw.get("subject_nm"),
        grade=raw.get("grade"),
        credit=raw.get("credit"),
        course_type=raw.get("course_type"),
        schedule_raw=sched.get("raw"),
        slots=[_slot_from_raw(s) for s in (sched.get("slots") or [])],
        rooms=list(sched.get("rooms") or []),
        enrolled=enr.get("enrolled"),
        capacity=enr.get("capacity"),
        syllabus=SyllabusInfo.from_raw(raw.get("syllabus")),
        raw=raw,
    )


def load_unified(path: Optional[Path] = None) -> Optional[UnifiedDoc]:
    """Load and cache the unified JSON. Returns None when the file is
    missing.

    Cache key is the file's mtime: if the bundled JSON is replaced by an
    app update, the next call notices the new mtime and re-parses. Within
    a process, the typical cost is one `stat` call per invocation."""
    p = path or _DEFAULT_PATH
    if not p.exists():
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    cached = _cache.get(p)
    if cached is not None and _cache_mtime.get(p) == mtime:
        return cached
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.exception("courses unified JSON parse failed: %s", p)
        return None

    courses = [_course_from_raw(r) for r in (doc.get("courses") or [])]
    by_key: dict[str, UnifiedCourse] = {}
    by_name: dict[str, UnifiedCourse] = {}
    for c in courses:
        if c.key and c.key not in by_key:
            by_key[c.key] = c
        if c.subject_nm and c.subject_nm not in by_name:
            by_name[c.subject_nm] = c

    year = int(doc.get("year") or 0)
    term = int(doc.get("term") or 0)
    semester = doc.get("semester") or f"{year}-{term:02d}"
    result = UnifiedDoc(
        path=p,
        year=year,
        term=term,
        semester=semester,
        courses=courses,
        by_key=by_key,
        by_name=by_name,
    )
    _cache[p] = result
    _cache_mtime[p] = mtime
    return result


def reset_cache() -> None:
    """Reload on next call. Used by tests."""
    _cache.clear()
    _cache_mtime.clear()


# ---------------------------------------------------------------------------
# Lookup

_CODE_RE = re.compile(r"^(?P<sub>\d+)_(?P<dv>\d{1,3})(?:_.*)?$")


def split_course_code(code: str) -> Optional[tuple[str, str]]:
    """'40121_01_U' -> ('40121', '01'). Returns None if format unknown."""
    if not code:
        return None
    m = _CODE_RE.match(code.strip())
    if not m:
        return None
    return m["sub"], m["dv"]


def find_by_course_code(code: str, *, doc: Optional[UnifiedDoc] = None) -> Optional[UnifiedCourse]:
    d = doc or load_unified()
    if d is None:
        return None
    parts = split_course_code(code)
    if not parts:
        return None
    return d.by_key.get(f"{parts[0]}_{parts[1]}")


def find_by_subject_dvcl(
    subject_no: str,
    dvcl_no: str,
    *,
    doc: Optional[UnifiedDoc] = None,
) -> Optional[UnifiedCourse]:
    d = doc or load_unified()
    if d is None:
        return None
    return d.by_key.get(f"{subject_no.strip()}_{dvcl_no.strip()}")


def find_by_name(
    name: str,
    *,
    doc: Optional[UnifiedDoc] = None,
) -> Optional[UnifiedCourse]:
    """Exact subject_nm match. Multiple dvcl entries collapse to the first.
    Use `find_by_course_code` when you need the right section."""
    d = doc or load_unified()
    if d is None or not name:
        return None
    return d.by_name.get(name.strip())


# ---------------------------------------------------------------------------
# Period → wall-clock time

_DEFAULT_PERIOD_TIMES: dict[int, tuple[str, str]] = {
    1: ("09:00", "09:50"),
    2: ("10:00", "10:50"),
    3: ("11:00", "11:50"),
    4: ("12:00", "12:50"),
    5: ("13:00", "13:50"),
    6: ("14:00", "14:50"),
    7: ("15:00", "15:50"),
    8: ("16:00", "16:50"),
    9: ("17:00", "17:50"),
    10: ("18:00", "18:50"),
    11: ("19:00", "19:50"),
    12: ("20:00", "20:50"),
    13: ("21:00", "21:50"),
    14: ("22:00", "22:50"),
}


def _period_table() -> dict[int, tuple[str, str]]:
    override = os.environ.get("UOS_PERIOD_TIMES")
    if not override:
        return _DEFAULT_PERIOD_TIMES
    try:
        raw = json.loads(override)
        table = {int(k): (v[0], v[1]) for k, v in raw.items()}
        return table or _DEFAULT_PERIOD_TIMES
    except Exception:
        log.warning("UOS_PERIOD_TIMES env var unreadable; using defaults")
        return _DEFAULT_PERIOD_TIMES


_KO_WEEKDAY = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def slot_to_times(slot: ScheduleSlot) -> Optional[tuple[int, str, str, Optional[str]]]:
    """Convert a (weekday, periods[]) slot to a (weekday_int, start, end, room).

    The start is the first period's start; the end is the last period's
    end. Returns None when the slot lacks a Korean weekday or periods.
    """
    if not slot.weekday or slot.weekday not in _KO_WEEKDAY:
        return None
    if not slot.periods:
        return None
    table = _period_table()
    first_p, last_p = min(slot.periods), max(slot.periods)
    if first_p not in table or last_p not in table:
        return None
    start = table[first_p][0]
    end = table[last_p][1]
    return (_KO_WEEKDAY[slot.weekday], start, end, slot.room)
