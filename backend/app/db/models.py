from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from datetime import datetime

from .database import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)

    moodle_course_id = Column(Integer, unique=True, index=True, nullable=False)
    course_url = Column(String, nullable=False)
    course_code = Column(String)
    course_name = Column(String, nullable=False)
    professor = Column(String)
    semester = Column(String)

    last_synced_at = Column(DateTime)


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    cmid = Column(Integer, index=True, nullable=False)
    title = Column(String)
    due_at = Column(DateTime)
    description_html = Column(Text)
    url = Column(String)
    submitted = Column(Boolean, default=False)

    # Activity name from the course flat page. Drives the on-disk folder
    # (Desktop/UOS_LMS_AI/<course>/<source_label>/) and DOCX placement.
    source_label = Column(String)

    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("course_id", "cmid", name="uq_assignment_course_cmid"),)


class Notice(Base):
    __tablename__ = "notices"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    cmid = Column(Integer, index=True, nullable=False)
    bwid = Column(Integer, index=True, nullable=False)

    title = Column(String)
    author = Column(String)
    posted_at = Column(DateTime)
    body_html = Column(Text)
    url = Column(String)

    source_label = Column(String)  # parent board's activity name

    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("course_id", "cmid", "bwid", name="uq_notice_course_cmid_bwid"),)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=True)

    cmid = Column(Integer, index=True)
    source_type = Column(String, nullable=False)  # folder | ubboard_attach | assign_attach
    # Sanitized activity name (e.g. "강의자료실", "공지사항", "1주차 과제").
    # On-disk layout is Desktop/UOS_LMS_AI/<course>/<source_label>/원본/<file>.
    source_label = Column(String)
    week = Column(Integer)  # metadata only — paths no longer key on week
    post_id = Column(Integer)  # ubboard bwid

    title = Column(String)
    file_path = Column(String)
    file_type = Column(String)
    download_url = Column(String)
    sha256 = Column(String(64), index=True)
    size_bytes = Column(Integer)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="downloaded")

    # Parsing pipeline state (PyMuPDF + PaddleOCR).
    # pending | running | done | failed | skipped
    parse_status = Column(String, default="pending", index=True)
    parsed_at = Column(DateTime, nullable=True)
    parse_error = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("course_id", "sha256", name="uq_material_course_sha"),)


class Summary(Base):
    """AI-generated summary. Kept for future re-enablement — currently not
    populated and not read by docx_writer. See plan ai-purring-goose."""
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"))

    summary_md = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ParsedContent(Base):
    """Output of the parser pipeline. One row per material. Block-level
    detail lives in `blocks_json_path` as a JSON file under
    backend/data/parsed/<material_id>.json."""
    __tablename__ = "parsed_contents"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), unique=True, nullable=False)

    parser_version = Column(String, nullable=False)
    used_ocr = Column(Boolean, default=False)
    plain_text = Column(Text)
    blocks_json_path = Column(String)
    page_count = Column(Integer)
    char_count = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)


class Timetable(Base):
    """Per-course weekly slot. Source = "api" (UCLASS timetable JSON) or
    "syllabus" (parsed from CourseSyllabus.schedule_json)."""
    __tablename__ = "timetable_slots"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    weekday = Column(Integer, nullable=False)  # 0=Mon .. 6=Sun
    start_time = Column(String)  # "13:00"
    end_time = Column(String)
    location = Column(String, nullable=True)
    source = Column(String, default="api")

    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("course_id", "weekday", "start_time", name="uq_timetable_course_slot"),
    )


class CourseSyllabus(Base):
    """Cached 수업계획서 PDF + parsed schedule (per-week topics)."""
    __tablename__ = "course_syllabi"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), unique=True, nullable=False)

    pdf_path = Column(String)
    parsed_text = Column(Text)
    schedule_json = Column(Text)  # JSON: [{week, topic, ...}]
    fetched_at = Column(DateTime, default=datetime.utcnow)
