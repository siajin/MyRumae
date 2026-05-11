"""Database upsert helpers. Synchronous SQLAlchemy on the existing engine."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import (
    Assignment,
    Course,
    CourseSyllabus,
    Material,
    Notice,
    ParsedContent,
    Summary,
    Timetable,
)


def session_scope() -> Session:
    return SessionLocal()


# --- Course ---------------------------------------------------------------

def upsert_course(
    db: Session,
    *,
    moodle_course_id: int,
    course_url: str,
    course_name: str,
    professor: Optional[str] = None,
    semester: Optional[str] = None,
    course_code: Optional[str] = None,
) -> Course:
    course = (
        db.query(Course)
        .filter(Course.moodle_course_id == moodle_course_id)
        .one_or_none()
    )
    if course is None:
        course = Course(moodle_course_id=moodle_course_id, course_url=course_url, course_name=course_name)
        db.add(course)
    course.course_url = course_url
    course.course_name = course_name
    if professor is not None:
        course.professor = professor
    if semester is not None:
        course.semester = semester
    if course_code is not None:
        course.course_code = course_code
    db.flush()
    return course


def mark_course_synced(db: Session, course_id: int) -> None:
    course = db.get(Course, course_id)
    if course is not None:
        course.last_synced_at = datetime.utcnow()


def course_activity_counts(db: Session, course_id: int) -> dict:
    """Single-shot counts for the UI Course card."""
    return {
        "notices": db.query(Notice).filter(Notice.course_id == course_id).count(),
        "materials": db.query(Material).filter(Material.course_id == course_id).count(),
        "assignments": db.query(Assignment).filter(Assignment.course_id == course_id).count(),
    }


# --- Material -------------------------------------------------------------

def material_exists_by_sha(db: Session, course_id: int, sha256: str) -> bool:
    return (
        db.query(Material)
        .filter(Material.course_id == course_id, Material.sha256 == sha256)
        .first()
        is not None
    )


def material_exists_by_filename(db: Session, course_id: int, filename: str) -> bool:
    """Pre-download dedupe — true when this course already has a Material
    with the same `title` (= original/suggested filename) on disk.

    Used so we can skip the network round-trip when the LMS still serves a
    file with a name we've already saved. SHA256 remains the post-download
    authoritative key (catches re-uploads under the same filename)."""
    if not filename:
        return False
    return (
        db.query(Material)
        .filter(Material.course_id == course_id, Material.title == filename)
        .first()
        is not None
    )


def insert_material(
    db: Session,
    *,
    course_id: int,
    source_type: str,
    title: Optional[str],
    file_path: str,
    file_type: Optional[str],
    download_url: Optional[str],
    sha256: str,
    size_bytes: int,
    cmid: Optional[int] = None,
    week: Optional[int] = None,
    source_label: Optional[str] = None,
    post_id: Optional[int] = None,
    assignment_id: Optional[int] = None,
) -> Material:
    m = Material(
        course_id=course_id,
        assignment_id=assignment_id,
        source_type=source_type,
        cmid=cmid,
        week=week,
        source_label=source_label,
        post_id=post_id,
        title=title,
        file_path=file_path,
        file_type=file_type,
        download_url=download_url,
        sha256=sha256,
        size_bytes=size_bytes,
    )
    db.add(m)
    db.flush()
    return m


def materials_for_course(db: Session, course_id: int) -> list[Material]:
    return (
        db.query(Material)
        .filter(Material.course_id == course_id)
        .order_by(Material.source_label.asc(), Material.uploaded_at.asc())
        .all()
    )


def materials_pending_parse(db: Session, course_id: Optional[int] = None) -> list[Material]:
    """Materials that still need parsing (or have failed and can be retried)."""
    q = db.query(Material).filter(Material.parse_status.in_(("pending", "failed")))
    if course_id is not None:
        q = q.filter(Material.course_id == course_id)
    return q.order_by(Material.id.asc()).all()


def set_material_parse_status(
    db: Session,
    material_id: int,
    status: str,
    *,
    error: Optional[str] = None,
) -> None:
    m = db.get(Material, material_id)
    if m is None:
        return
    m.parse_status = status
    m.parse_error = error
    if status == "done":
        m.parsed_at = datetime.utcnow()
    db.flush()


# --- Notice ---------------------------------------------------------------

def upsert_notice(
    db: Session,
    *,
    course_id: int,
    cmid: int,
    bwid: int,
    title: Optional[str],
    author: Optional[str],
    posted_at: Optional[datetime],
    body_html: Optional[str],
    url: Optional[str],
    source_label: Optional[str] = None,
) -> Notice:
    notice = (
        db.query(Notice)
        .filter(Notice.course_id == course_id, Notice.cmid == cmid, Notice.bwid == bwid)
        .one_or_none()
    )
    if notice is None:
        notice = Notice(course_id=course_id, cmid=cmid, bwid=bwid)
        db.add(notice)
    notice.title = title
    notice.author = author
    notice.posted_at = posted_at
    notice.body_html = body_html
    notice.url = url
    if source_label is not None:
        notice.source_label = source_label
    notice.fetched_at = datetime.utcnow()
    db.flush()
    return notice


# --- Assignment -----------------------------------------------------------

def upsert_assignment(
    db: Session,
    *,
    course_id: int,
    cmid: int,
    title: Optional[str],
    due_at: Optional[datetime],
    description_html: Optional[str],
    url: Optional[str],
    submitted: bool = False,
    source_label: Optional[str] = None,
) -> Assignment:
    a = (
        db.query(Assignment)
        .filter(Assignment.course_id == course_id, Assignment.cmid == cmid)
        .one_or_none()
    )
    if a is None:
        a = Assignment(course_id=course_id, cmid=cmid)
        db.add(a)
    a.title = title
    a.due_at = due_at
    a.description_html = description_html
    a.url = url
    a.submitted = submitted
    if source_label is not None:
        a.source_label = source_label
    a.fetched_at = datetime.utcnow()
    db.flush()
    return a


# --- Summary (kept for future AI re-enablement; not called) ---------------

def upsert_summary(
    db: Session,
    *,
    material_id: int,
    summary_md: str,
) -> Summary:
    """One Summary per material (latest wins). Currently not invoked —
    docx_writer no longer reads Summary. Kept so AI can be re-enabled later
    without restoring this function. See plan ai-purring-goose."""
    s = (
        db.query(Summary)
        .filter(Summary.material_id == material_id)
        .one_or_none()
    )
    if s is None:
        s = Summary(material_id=material_id)
        db.add(s)
    s.summary_md = summary_md
    s.created_at = datetime.utcnow()
    db.flush()
    return s


# --- ParsedContent --------------------------------------------------------

def upsert_parsed_content(
    db: Session,
    *,
    material_id: int,
    parser_version: str,
    used_ocr: bool,
    plain_text: str,
    blocks_json_path: str,
    page_count: int,
    char_count: int,
) -> ParsedContent:
    pc = (
        db.query(ParsedContent)
        .filter(ParsedContent.material_id == material_id)
        .one_or_none()
    )
    if pc is None:
        pc = ParsedContent(material_id=material_id)
        db.add(pc)
    pc.parser_version = parser_version
    pc.used_ocr = used_ocr
    pc.plain_text = plain_text
    pc.blocks_json_path = blocks_json_path
    pc.page_count = page_count
    pc.char_count = char_count
    pc.created_at = datetime.utcnow()
    db.flush()
    return pc


def get_parsed_content(db: Session, material_id: int) -> Optional[ParsedContent]:
    return (
        db.query(ParsedContent)
        .filter(ParsedContent.material_id == material_id)
        .one_or_none()
    )


# --- Timetable ------------------------------------------------------------

def upsert_timetable_slot(
    db: Session,
    *,
    course_id: int,
    weekday: int,
    start_time: str,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    source: str = "api",
) -> Timetable:
    slot = (
        db.query(Timetable)
        .filter(
            Timetable.course_id == course_id,
            Timetable.weekday == weekday,
            Timetable.start_time == start_time,
        )
        .one_or_none()
    )
    if slot is None:
        slot = Timetable(course_id=course_id, weekday=weekday, start_time=start_time)
        db.add(slot)
    slot.end_time = end_time
    slot.location = location
    slot.source = source
    slot.fetched_at = datetime.utcnow()
    db.flush()
    return slot


# --- Syllabus -------------------------------------------------------------

def upsert_syllabus(
    db: Session,
    *,
    course_id: int,
    schedule_json: Optional[str] = None,
) -> CourseSyllabus:
    # NOTE: CourseSyllabus.pdf_path / parsed_text columns are intentionally
    # kept in the schema but no longer accepted here — currently no caller
    # caches the syllabus PDF. Re-add the params if PDF caching returns.
    syl = (
        db.query(CourseSyllabus)
        .filter(CourseSyllabus.course_id == course_id)
        .one_or_none()
    )
    if syl is None:
        syl = CourseSyllabus(course_id=course_id)
        db.add(syl)
    if schedule_json is not None:
        syl.schedule_json = schedule_json
    syl.fetched_at = datetime.utcnow()
    db.flush()
    return syl
