"""Database upsert helpers. Synchronous SQLAlchemy on the existing engine."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Assignment, Course, Material, Notice, Summary


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
    course = db.query(Course).get(course_id)
    if course is not None:
        course.last_synced_at = datetime.utcnow()


# --- Material -------------------------------------------------------------

def material_exists_by_sha(db: Session, course_id: int, sha256: str) -> bool:
    return (
        db.query(Material)
        .filter(Material.course_id == course_id, Material.sha256 == sha256)
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
    post_id: Optional[int] = None,
    assignment_id: Optional[int] = None,
) -> Material:
    m = Material(
        course_id=course_id,
        assignment_id=assignment_id,
        source_type=source_type,
        cmid=cmid,
        week=week,
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
    notice.fetched_at = datetime.utcnow()
    db.flush()
    return notice


# --- Assignment -----------------------------------------------------------

# --- Summary --------------------------------------------------------------

def upsert_summary(
    db: Session,
    *,
    material_id: int,
    summary_md: str,
) -> Summary:
    """One Summary per material (latest wins). Markdown stays internal —
    user-facing rendering is DOCX via app.docs.docx_writer."""
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


def materials_for_course_week(
    db: Session,
    course_id: int,
    week: Optional[int],
) -> list[Material]:
    q = db.query(Material).filter(Material.course_id == course_id)
    if week is None:
        q = q.filter(Material.week.is_(None))
    else:
        q = q.filter(Material.week == week)
    return q.order_by(Material.uploaded_at.asc()).all()


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
    a.fetched_at = datetime.utcnow()
    db.flush()
    return a
