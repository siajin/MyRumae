"""PDF text extraction.

Strategy per page:
  1. PyMuPDF `page.get_text("blocks")` — fast and gives bbox + reading order.
  2. If extracted char count < threshold AND a non-trivial image area is
     present, render the page to a 200-dpi PNG and run PaddleOCR.
  3. If PyMuPDF is unavailable for some reason, fall back to pdfplumber
     page-level text (no bbox).

The page index is 1-based in our Block.page (matches PDF/PPT slide numbers
users see).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..events import emit
from . import ocr as ocr_mod
from .blocks import Block, ParseResult

log = logging.getLogger(__name__)

# A page with fewer than this many printable characters is considered
# text-poor and a candidate for OCR.
_TEXT_POOR_THRESHOLD = 20

# Render at this dpi when handing the page to OCR.
_OCR_RENDER_DPI = 200


def _pymupdf_version() -> str:
    try:
        import fitz
        return getattr(fitz, "__version__", "unknown")
    except Exception:
        return "unavailable"


def parser_version() -> str:
    return f"pymupdf-{_pymupdf_version()}+paddleocr-{ocr_mod.version()}"


_mupdf_silenced = False


def _ensure_mupdf_silent() -> None:
    """MuPDF's C layer writes parser warnings ("syntax error: invalid key in
    dict", etc.) directly to a file descriptor we don't control, sometimes fd 1
    (stdout) — which collides with our JSON Lines event contract and surfaces
    on the Tauri side as 'non-json stdout line' raw-line events. Disable that
    channel; warnings remain accessible via TOOLS.mupdf_warnings() and we drain
    them to stderr per parse so nothing is silently lost."""
    global _mupdf_silenced
    if _mupdf_silenced:
        return
    try:
        import fitz
        fitz.TOOLS.mupdf_display_errors(False)
        # discard whatever was buffered before we got control
        try:
            fitz.TOOLS.mupdf_warnings(reset=True)
        except Exception:
            pass
        _mupdf_silenced = True
    except Exception:
        # fitz unavailable — caller will fall back to pdfplumber.
        pass


def _drain_mupdf_warnings(path: Path) -> None:
    try:
        import fitz
        warnings = fitz.TOOLS.mupdf_warnings(reset=True)
    except Exception:
        return
    if warnings:
        # logging → stderr → tracing::debug on Rust side, no JSON pollution.
        log.debug("MuPDF warnings for %s:\n%s", path, warnings)


def extract_pdf(
    path: Path,
    *,
    material_id: Optional[int] = None,
    enable_ocr: bool = True,
) -> ParseResult:
    """Parse a PDF into blocks. Emits parse_progress per page."""
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        log.error("PyMuPDF unavailable: %s — falling back to pdfplumber", e)
        return _pdfplumber_fallback(path)

    _ensure_mupdf_silent()

    result = ParseResult(parser_version=parser_version())
    try:
        doc = fitz.open(str(path))
    except Exception:
        log.exception("PyMuPDF failed to open %s", path)
        return _pdfplumber_fallback(path)

    try:
        result.page_count = doc.page_count
        for page_idx in range(doc.page_count):
            page_num = page_idx + 1
            try:
                page = doc.load_page(page_idx)
                raw_blocks = page.get_text("blocks") or []
                page_blocks: list[Block] = []
                for order, b in enumerate(raw_blocks):
                    # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
                    if len(b) < 5:
                        continue
                    x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                    text = (text or "").strip()
                    if not text:
                        continue
                    page_blocks.append(
                        Block(
                            page=page_num,
                            kind="text",
                            text=text,
                            bbox=(float(x0), float(y0), float(x1), float(y1)),
                            order=order,
                        )
                    )

                page_char_count = sum(len(b.text) for b in page_blocks)
                if enable_ocr and page_char_count < _TEXT_POOR_THRESHOLD:
                    # Likely a scanned page — fall back to OCR.
                    if ocr_mod.is_available():
                        png = page.get_pixmap(dpi=_OCR_RENDER_DPI).tobytes("png")
                        ocr_blocks = ocr_mod.ocr_image_bytes(png, page=page_num)
                        if ocr_blocks:
                            result.used_ocr = True
                            page_blocks = ocr_blocks
                    else:
                        log.debug("OCR unavailable; leaving text-poor page %d as-is", page_num)

                result.blocks.extend(page_blocks)

                if material_id is not None:
                    emit(
                        "parse_progress",
                        material_id=material_id,
                        page=page_num,
                        total_pages=doc.page_count,
                    )
            except Exception:
                log.exception("page %d parse failed in %s", page_num, path)
    finally:
        doc.close()
        _drain_mupdf_warnings(path)

    return result


def _pdfplumber_fallback(path: Path) -> ParseResult:
    """Last-resort text extraction. No bbox, no OCR."""
    try:
        import pdfplumber
    except Exception:
        log.error("pdfplumber also unavailable; returning empty parse for %s", path)
        return ParseResult(parser_version="empty-fallback")

    result = ParseResult(parser_version=f"pdfplumber-{getattr(pdfplumber, '__version__', '?')}")
    try:
        with pdfplumber.open(str(path)) as pdf:
            result.page_count = len(pdf.pages)
            for idx, page in enumerate(pdf.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    result.blocks.append(Block(page=idx + 1, kind="text", text=text, order=0))
    except Exception:
        log.exception("pdfplumber failed on %s", path)
    return result
