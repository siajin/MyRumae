"""Master course catalog DB applier.

Source of truth = the bundled unified JSON at
`backend/data/master/courses_2026_1.json` (shipped with the app, updated
via app-store releases). The hand-curated `course_catalog.json` path was
removed — the unified JSON already covers every UOS course for the term.

Matching against UCLASS Course rows uses, in order:
  1. exact `course_code` match (e.g. "40121_01_U")
  2. exact `course_name` match
  3. normalized `course_name` match (whitespace + parenthesis stripped,
     case-folded)
Year/term, when present on the entry, must also match `Course.semester`
(e.g. "2026-10").
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import Course
from . import courses_index

log = logging.getLogger(__name__)


_SEMESTER_RE = re.compile(r"^(?P<year>\d{4})-(?P<term>\d{2})$")


# ---------------------------------------------------------------------------
# Schema

@dataclass
class CatalogSlot:
    weekday: int                       # 0=Mon .. 6=Sun
    start_time: str                    # "13:00"
    end_time: Optional[str] = None
    location: Optional[str] = None


@dataclass
class CatalogEntry:
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    year: Optional[int] = None
    term: Optional[int] = None
    professor: Optional[str] = None
    credit: Optional[int] = None
    slots: list[CatalogSlot] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class CatalogLoadResult:
    path: Path
    exists: bool
    entries: list[CatalogEntry] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader: unified master JSON → CatalogEntry list

def _entry_from_unified(uc: "courses_index.UnifiedCourse", semester: str) -> Optional[CatalogEntry]:
    """Convert a UnifiedCourse row into a CatalogEntry. Entries with no
    resolvable wall-clock slot are still emitted so they can fill
    professor/credit."""
    slots: list[CatalogSlot] = []
    for s in uc.slots:
        mapped = courses_index.slot_to_times(s)
        if mapped is None:
            continue
        weekday, start, end, room = mapped
        slots.append(CatalogSlot(
            weekday=weekday, start_time=start, end_time=end, location=room
        ))

    # course_code "<sub>_<dv>_U" mirrors the UCLASS title convention.
    course_code = f"{uc.subject_no}_{uc.dvcl_no}_U" if uc.subject_no and uc.dvcl_no else None
    year, _, term = semester.partition("-")
    try:
        year_i = int(year) if year else None
        term_i = int(term) if term else None
    except ValueError:
        year_i, term_i = None, None

    return CatalogEntry(
        course_code=course_code,
        course_name=uc.subject_nm,
        year=year_i,
        term=term_i,
        professor=(uc.syllabus.professor if uc.syllabus else None),
        credit=uc.credit if isinstance(uc.credit, int) else None,
        slots=slots,
        raw={"_source": "unified_json", "key": uc.key},
    )


def load_unified_as_catalog(
    path: Optional[Path] = None,
) -> CatalogLoadResult:
    """Build a CatalogLoadResult from the bundled master JSON."""
    doc = courses_index.load_unified(path)
    p = path or courses_index.default_path()
    result = CatalogLoadResult(path=p, exists=doc is not None)
    if doc is None:
        return result
    for uc in doc.courses:
        entry = _entry_from_unified(uc, doc.semester)
        if entry is None:
            continue
        result.entries.append(entry)
    return result


# ---------------------------------------------------------------------------
# Matching

def _normalize_name(s: str) -> str:
    """Strip parenthesized fragments (e.g. '(01)' or '(2026-10, 40121_01_U)'),
    collapse whitespace, and case-fold."""
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\s+", "", s)
    return s.casefold()


def _semester_to_pair(sem: str) -> Optional[tuple[int, int]]:
    m = _SEMESTER_RE.match((sem or "").strip())
    return (int(m["year"]), int(m["term"])) if m else None


def _semester_matches(entry: CatalogEntry, course: Course) -> bool:
    """If the catalog entry doesn't specify year/term, accept any.
    If it does, require Course.semester to match."""
    if entry.year is None and entry.term is None:
        return True
    sem = _semester_to_pair(course.semester or "")
    if sem is None:
        # Catalog asks for a specific semester but the Course doesn't know
        # which semester it is — refuse to bind (safer).
        return False
    y, t = sem
    if entry.year is not None and entry.year != y:
        return False
    if entry.term is not None and entry.term != t:
        return False
    return True


@dataclass
class MatchResult:
    entry: Optional[CatalogEntry]
    via: str                 # "code" | "name" | "name_normalized" | "none"


def match_course(entries: list[CatalogEntry], course: Course) -> MatchResult:
    code = (course.course_code or "").strip()
    name = (course.course_name or "").strip()
    name_norm = _normalize_name(name)

    # 1) exact course_code
    if code:
        for e in entries:
            if e.course_code and e.course_code.strip() == code and _semester_matches(e, course):
                return MatchResult(entry=e, via="code")

    # 2) exact course_name
    if name:
        for e in entries:
            if e.course_name and e.course_name.strip() == name and _semester_matches(e, course):
                return MatchResult(entry=e, via="name")

    # 3) normalized course_name
    if name_norm:
        for e in entries:
            if e.course_name and _normalize_name(e.course_name) == name_norm and _semester_matches(e, course):
                return MatchResult(entry=e, via="name_normalized")

    return MatchResult(entry=None, via="none")


# ---------------------------------------------------------------------------
# Apply to DB

@dataclass
class ApplyResult:
    total_courses: int = 0
    matched: int = 0
    unmatched: int = 0
    slots_upserted: int = 0
    professor_filled: int = 0
    syllabus_weeks_written: int = 0
    per_course: list[dict] = field(default_factory=list)


def apply_catalog_to_db(
    db: Session,
    *,
    path: Optional[Path] = None,
) -> tuple[CatalogLoadResult, ApplyResult]:
    """Apply master-JSON timetable + professor + syllabus weeks to DB Courses.

    Returns the load result (so callers can surface entries=0 / missing file)
    and an ApplyResult with per-course rows for event emission.
    """
    load = load_unified_as_catalog(path)
    apply_result = ApplyResult()

    courses = db.query(Course).order_by(Course.id.asc()).all()
    apply_result.total_courses = len(courses)

    if not load.exists or not load.entries:
        return load, apply_result

    # Pre-load unified doc for syllabus weekly topics (cheap — already cached
    # by `load_unified_as_catalog` above via shared mtime cache).
    unified_doc = courses_index.load_unified(path)

    for course in courses:
        match = match_course(load.entries, course)
        row = {
            "course_id": course.id,
            "course_name": course.course_name,
            "course_code": course.course_code,
            "matched_via": match.via,
            "slots": 0,
        }
        if match.entry is None:
            apply_result.unmatched += 1
        else:
            apply_result.matched += 1

            for s in match.entry.slots:
                repo.upsert_timetable_slot(
                    db,
                    course_id=course.id,
                    weekday=s.weekday,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    location=s.location,
                    source="master",
                )
                apply_result.slots_upserted += 1
                row["slots"] += 1

            if match.entry.professor and not course.professor:
                course.professor = match.entry.professor
                db.flush()
                apply_result.professor_filled += 1
                row["professor_filled"] = True

        # Independent: enrich syllabus weekly topics by course_code.
        if unified_doc is not None and course.course_code:
            uc = courses_index.find_by_course_code(course.course_code, doc=unified_doc)
            if uc is not None and uc.syllabus is not None:
                weeks_payload = [
                    {
                        "week": w.week,
                        "topic": w.topic,
                        "method": w.method,
                        "assignment": w.assignment,
                        "goal": w.goal,
                    }
                    for w in uc.syllabus.weeks
                ]
                if weeks_payload:
                    repo.upsert_syllabus(
                        db,
                        course_id=course.id,
                        schedule_json=json.dumps(weeks_payload, ensure_ascii=False),
                    )
                    row["syllabus_weeks"] = len(weeks_payload)
                    apply_result.syllabus_weeks_written += len(weeks_payload)
                if uc.syllabus.professor and not course.professor:
                    course.professor = uc.syllabus.professor
                    apply_result.professor_filled += 1
                    row.setdefault("professor_filled", True)
                db.flush()

        apply_result.per_course.append(row)

    db.commit()
    return load, apply_result
