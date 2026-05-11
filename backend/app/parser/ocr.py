"""OCR is disabled in the demo build.

Why this file still exists:
- The PDF parser ([pdf.py](pdf.py)) calls `ocr_mod.is_available()` to decide
  whether to render a text-poor page to PNG and OCR it. With this stub
  it always answers "unavailable", so pages that came from a scanned PDF
  end up with empty body in DOCX — that's the expected demo behavior.

How to re-enable (later):
  1. `pip install paddleocr paddlepaddle` (or another OCR backend)
  2. set env var `MYRUMAE_ENABLE_OCR=1`
  3. swap this stub back to a real PaddleOCR wrapper — the
     `is_available()` / `version()` / `ocr_image_bytes()` shape is what
     the rest of the parser expects.

Nothing else (DB schema, ParsedContent.used_ocr, event names) needs to
change to bring OCR back.
"""
from __future__ import annotations

import logging
import os
from typing import List

from .blocks import Block

log = logging.getLogger(__name__)

_DEMO_DISABLED = os.environ.get("MYRUMAE_ENABLE_OCR", "0") not in ("1", "true", "yes")

if _DEMO_DISABLED:
    log.debug("OCR disabled in demo build (set MYRUMAE_ENABLE_OCR=1 to re-enable)")


def is_available() -> bool:
    return False


def version() -> str:
    return "disabled"


def ocr_image_bytes(png_bytes: bytes, *, page: int) -> List[Block]:
    # Intentionally empty: pdf.py will only call this when is_available()
    # returns True, but we keep the signature stable for the future.
    return []
