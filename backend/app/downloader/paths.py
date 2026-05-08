"""Filesystem path helpers for downloaded materials.

User-facing layout (per spec):

    Desktop/UOS_LMS_AI/
        <course_name>/
            <N>주차/
                원본/    # PDF / PPTX / DOCX downloads
                정리/    # generated DOCX summaries

A scratch TEMP_ROOT under backend/data/temp is used as a staging area while
Playwright is downloading; files are moved into the Desktop tree only after
the dedupe check passes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# backend/ root, resolved relative to this file so it works from any CWD.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_ROOT = _BACKEND_ROOT / "data" / "temp"

DESKTOP_FOLDER_NAME = "UOS_LMS_AI"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_segment(name: str, *, fallback: str = "_") -> str:
    if not name:
        return fallback
    cleaned = _INVALID_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned or fallback


def desktop_root() -> Path:
    """User's Desktop/UOS_LMS_AI directory. Created lazily by callers."""
    return Path.home() / "Desktop" / DESKTOP_FOLDER_NAME


def _week_segment(week: Optional[int]) -> str:
    return f"{week}주차" if week is not None else "기타"


def course_dir(course_name: str) -> Path:
    return desktop_root() / sanitize_segment(course_name or "unknown_course")


def week_dir(course_name: str, week: Optional[int]) -> Path:
    return course_dir(course_name) / _week_segment(week)


def original_dir(course_name: str, week: Optional[int]) -> Path:
    return week_dir(course_name, week) / "원본"


def summary_dir(course_name: str, week: Optional[int]) -> Path:
    return week_dir(course_name, week) / "정리"


def original_path(course_name: str, week: Optional[int], filename: str) -> Path:
    return original_dir(course_name, week) / sanitize_segment(filename)


def ensure_dirs() -> None:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    desktop_root().mkdir(parents=True, exist_ok=True)
