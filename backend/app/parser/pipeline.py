"""Public parsing entry point. Dispatches by file extension and stores
results both as a ParsedContent row (DB) and a per-material JSON file
(backend/data/parsed/<id>.json) for the UI viewer.
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import Material
from ..events import emit
from . import office as office_mod
from . import pdf as pdf_mod
from .blocks import ParseResult, write_blocks_json

log = logging.getLogger(__name__)

# Anchored absolute path so behavior is CWD-independent (per CLAUDE.md rule 1).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
PARSED_DIR = _BACKEND_ROOT / "data" / "user" / "parsed"


_PDF_EXTS = {"pdf"}
_OFFICE_EXTS = {"pptx", "docx"}   # text-only via office.py (no OCR/images)
_SKIP_EXTS = {"zip", "hwp", "xlsx", "xls", "txt", "jpg", "jpeg", "png"}


def _ext_of(material: Material) -> str:
    ext = (material.file_type or "").lower().lstrip(".")
    if ext:
        return ext
    if material.file_path:
        return Path(material.file_path).suffix.lstrip(".").lower()
    return ""


def _blocks_path(material_id: int) -> Path:
    return PARSED_DIR / f"{material_id}.json"


def parse_material(db: Session, material_id: int) -> dict:
    """Parse one material end-to-end. Idempotent — overwrites on re-run.

    Returns a small summary dict for the caller. Never raises: failures are
    captured into Material.parse_status='failed' + parse_error and emitted
    as a parse_failed event so the UI keeps moving.
    """
    material = db.get(Material, material_id)
    if material is None:
        emit("parse_failed", level="error", material_id=material_id, reason="material_missing")
        return {"status": "failed", "reason": "material_missing"}

    ext = _ext_of(material)
    file_path = Path(material.file_path) if material.file_path else None

    emit(
        "parse_started",
        material_id=material_id,
        file_type=ext or "unknown",
        title=material.title or "",
    )

    if not file_path or not file_path.exists():
        repo.set_material_parse_status(db, material_id, "failed", error="file_missing")
        db.commit()
        emit("parse_failed", level="error", material_id=material_id, reason="file_missing")
        return {"status": "failed", "reason": "file_missing"}

    if ext in _SKIP_EXTS:
        repo.set_material_parse_status(db, material_id, "skipped", error=f"unsupported:{ext}")
        db.commit()
        emit("parse_done", material_id=material_id, blocks=0, used_ocr=False, skipped=True)
        return {"status": "skipped", "ext": ext}

    if ext not in _PDF_EXTS and ext not in _OFFICE_EXTS:
        repo.set_material_parse_status(db, material_id, "skipped", error=f"unknown_ext:{ext}")
        db.commit()
        emit("parse_done", material_id=material_id, blocks=0, used_ocr=False, skipped=True)
        return {"status": "skipped", "ext": ext}

    repo.set_material_parse_status(db, material_id, "running")
    db.commit()

    try:
        if ext in _PDF_EXTS:
            result: ParseResult = pdf_mod.extract_pdf(file_path, material_id=material_id)
        else:
            result = office_mod.extract_office(file_path, material_id=material_id)
    except Exception as e:
        tb = traceback.format_exc(limit=4)
        log.exception("parse_material(%d) failed", material_id)
        repo.set_material_parse_status(db, material_id, "failed", error=str(e)[:500])
        db.commit()
        emit("parse_failed", level="error", material_id=material_id, reason=str(e), traceback=tb)
        return {"status": "failed", "reason": str(e)}

    blocks_json_path = _blocks_path(material_id)
    write_blocks_json(blocks_json_path, result.blocks)

    repo.upsert_parsed_content(
        db,
        material_id=material_id,
        parser_version=result.parser_version,
        used_ocr=result.used_ocr,
        plain_text=result.plain_text(),
        blocks_json_path=str(blocks_json_path),
        page_count=result.page_count,
        char_count=result.char_count(),
    )
    repo.set_material_parse_status(db, material_id, "done")
    db.commit()

    emit(
        "parse_done",
        material_id=material_id,
        blocks=len(result.blocks),
        pages=result.page_count,
        chars=result.char_count(),
        used_ocr=result.used_ocr,
    )
    return {
        "status": "done",
        "blocks": len(result.blocks),
        "pages": result.page_count,
        "used_ocr": result.used_ocr,
    }


def parse_materials(db: Session, material_ids: Iterable[int]) -> dict:
    """Convenience batch wrapper. Returns aggregated counts."""
    totals = {"done": 0, "failed": 0, "skipped": 0}
    for mid in material_ids:
        try:
            res = parse_material(db, mid)
            status = res.get("status", "failed")
            if status in totals:
                totals[status] += 1
            else:
                totals.setdefault(status, 0)
                totals[status] += 1
        except Exception:
            log.exception("parse_materials: %d crashed", mid)
            totals["failed"] += 1
    return totals


def reparse_course(db: Session, course_id: Optional[int] = None) -> dict:
    """Force-reparse every pending/failed material (optionally one course)."""
    materials = repo.materials_pending_parse(db, course_id=course_id)
    return parse_materials(db, [m.id for m in materials])
