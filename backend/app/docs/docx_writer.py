"""User-facing DOCX summary generator (정리/ folder).

Per spec, raw markdown is never exposed to the user. We render structured
DOCX files with python-docx into Desktop/UOS_LMS_AI/<course>/<N>주차/정리/.

The summaries here are templated study notes built from collected material
metadata. AI-generated content can later be appended by populating the
Summary table and re-running this generator.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from sqlalchemy.orm import Session

from ..db.models import Course, Material, Summary
from ..downloader import paths

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queries

def _materials_for_week(db: Session, course_id: int, week: Optional[int]) -> List[Material]:
    q = db.query(Material).filter(Material.course_id == course_id)
    if week is None:
        q = q.filter(Material.week.is_(None))
    else:
        q = q.filter(Material.week == week)
    return q.order_by(Material.uploaded_at.asc()).all()


def _distinct_weeks(db: Session, course_id: int) -> List[Optional[int]]:
    rows = (
        db.query(Material.week)
        .filter(Material.course_id == course_id)
        .distinct()
        .all()
    )
    weeks = {row[0] for row in rows}
    # Numbered weeks first (ascending), "기타"/None bucket last
    return sorted(weeks, key=lambda w: (w is None, w if w is not None else 0))


def _summary_for_material(db: Session, material_id: int) -> Optional[str]:
    s = (
        db.query(Summary)
        .filter(Summary.material_id == material_id)
        .order_by(Summary.created_at.desc())
        .first()
    )
    return s.summary_md if s else None


# ---------------------------------------------------------------------------
# DOCX building blocks

def _set_korean_default_font(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(11)


def _add_meta(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    run_label = p.add_run(f"{label}: ")
    run_label.bold = True
    p.add_run(value)


def _add_section_heading(doc: Document, text: str) -> None:
    doc.add_heading(text, level=1)


def _add_bullet(doc: Document, text: str, *, bold: bool = False) -> None:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    if bold:
        run.bold = True


# ---------------------------------------------------------------------------
# Generators

def _week_label(week: Optional[int]) -> str:
    return f"{week}주차" if week is not None else "기타"


def generate_week_summary(
    db: Session,
    *,
    course: Course,
    week: Optional[int],
) -> Optional[Path]:
    """Write `<N>주차_강의정리.docx` for one (course, week).

    Returns the saved path, or None if the week has no materials yet.
    """
    materials = _materials_for_week(db, course.id, week)
    if not materials:
        return None

    out_dir = paths.summary_dir(course.course_name, week)
    out_dir.mkdir(parents=True, exist_ok=True)

    label = _week_label(week)
    out_path = out_dir / f"{label}_강의정리.docx"

    doc = Document()
    _set_korean_default_font(doc)

    title = doc.add_heading(f"{course.course_name} — {label} 강의 정리", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    _add_meta(doc, "과목", course.course_name)
    if course.course_code:
        _add_meta(doc, "강좌 코드", course.course_code)
    if course.professor:
        _add_meta(doc, "교수", course.professor)
    if course.semester:
        _add_meta(doc, "학기", course.semester)
    _add_meta(doc, "주차", label)
    _add_meta(doc, "생성일", datetime.now().strftime("%Y-%m-%d %H:%M"))

    doc.add_paragraph()

    # ---- 수집 자료 ------------------------------------------------------
    _add_section_heading(doc, "수집 자료")
    for m in materials:
        title_text = m.title or (Path(m.file_path).name if m.file_path else "(제목 없음)")
        type_tag = f"  [{m.file_type.upper()}]" if m.file_type else ""
        _add_bullet(doc, f"{title_text}{type_tag}", bold=True)

    doc.add_paragraph()

    # ---- 핵심 개념 ------------------------------------------------------
    _add_section_heading(doc, "핵심 개념")
    any_summary = False
    for m in materials:
        smd = _summary_for_material(db, m.id)
        if smd:
            any_summary = True
            sub = doc.add_paragraph()
            run = sub.add_run(m.title or "자료")
            run.bold = True
            for line in smd.splitlines():
                line = line.strip()
                if not line:
                    continue
                doc.add_paragraph(line)
    if not any_summary:
        doc.add_paragraph("(아직 정리된 핵심 개념이 없습니다. 자료를 학습한 뒤 채워주세요.)")

    # ---- 중요 내용 ------------------------------------------------------
    _add_section_heading(doc, "중요 내용")
    doc.add_paragraph("• ")
    doc.add_paragraph("• ")
    doc.add_paragraph("• ")

    # ---- 시험 포인트 ----------------------------------------------------
    _add_section_heading(doc, "시험 포인트")
    doc.add_paragraph("• ")
    doc.add_paragraph("• ")

    # ---- 복습 체크리스트 ------------------------------------------------
    _add_section_heading(doc, "복습 체크리스트")
    for m in materials:
        title_text = m.title or "자료"
        _add_bullet(doc, f"☐ {title_text} 1회 복습")
        _add_bullet(doc, f"☐ {title_text} 핵심 정리 작성")

    doc.save(str(out_path))
    log.info("DOCX summary written: %s", out_path)
    return out_path


def generate_course_summaries(db: Session, *, course: Course) -> List[Path]:
    """Generate DOCX summaries for every distinct week in this course."""
    written: List[Path] = []
    for w in _distinct_weeks(db, course.id):
        p = generate_week_summary(db, course=course, week=w)
        if p is not None:
            written.append(p)
    return written


def generate_all(db: Session) -> dict:
    """Re-render summaries for every course in the DB. Returns counts."""
    courses = db.query(Course).all()
    total = 0
    for c in courses:
        total += len(generate_course_summaries(db, course=c))
    return {"courses": len(courses), "docx_written": total}
