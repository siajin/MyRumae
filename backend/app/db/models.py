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

    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("course_id", "cmid", "bwid", name="uq_notice_course_cmid_bwid"),)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=True)

    cmid = Column(Integer, index=True)
    source_type = Column(String, nullable=False)  # folder | ubboard_attach | assign_attach
    week = Column(Integer)
    post_id = Column(Integer)  # ubboard bwid

    title = Column(String)
    file_path = Column(String)
    file_type = Column(String)
    download_url = Column(String)
    sha256 = Column(String(64), index=True)
    size_bytes = Column(Integer)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="downloaded")

    __table_args__ = (UniqueConstraint("course_id", "sha256", name="uq_material_course_sha"),)


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"))

    summary_md = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
