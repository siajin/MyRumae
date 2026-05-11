"""Filesystem path helpers for downloaded materials.

User-facing layout (post-refactor — organized by source activity, not week):

    Desktop/UOS_LMS_AI/
        <course_name>/
            <source_label>/   # e.g. 강의자료실, 공지사항, 1주차 과제
                원본/          # PDF / PPTX / DOCX downloads
                정리/          # one DOCX per source file (per material/notice/assignment)

`source_label` is the sanitized activity name captured on the course flat page
(`div.activityname`). Falls back to "기타" when missing.

A scratch TEMP_ROOT under backend/data/user/temp is used as a staging area
while Playwright is downloading; files are moved into the Desktop tree only
after the dedupe check passes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

# backend/ root, resolved relative to this file so it works from any CWD.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_ROOT = _BACKEND_ROOT / "data" / "user" / "temp"

DESKTOP_FOLDER_NAME = "UOS_LMS_AI"
FALLBACK_SOURCE = "기타"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_segment(name: str, *, fallback: str = "_") -> str:
    if not name:
        return fallback
    cleaned = _INVALID_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned or fallback


def desktop_root() -> Path:
    """User's Desktop/UOS_LMS_AI directory. Created lazily by callers."""
    return Path.home() / "Desktop" / DESKTOP_FOLDER_NAME


def _source_segment(source_label: Optional[str]) -> str:
    return sanitize_segment(source_label or FALLBACK_SOURCE, fallback=FALLBACK_SOURCE)


def course_dir(course_name: str) -> Path:
    return desktop_root() / sanitize_segment(course_name or "unknown_course")


def source_dir(course_name: str, source_label: Optional[str]) -> Path:
    return course_dir(course_name) / _source_segment(source_label)


def original_dir(course_name: str, source_label: Optional[str]) -> Path:
    return source_dir(course_name, source_label) / "원본"


def summary_dir(course_name: str, source_label: Optional[str]) -> Path:
    return source_dir(course_name, source_label) / "정리"


def original_path(course_name: str, source_label: Optional[str], filename: str) -> Path:
    return original_dir(course_name, source_label) / sanitize_segment(filename)


def ensure_dirs() -> None:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    desktop_root().mkdir(parents=True, exist_ok=True)


def filename_from_url(href: Optional[str]) -> Optional[str]:
    """Extract the filename from a Moodle pluginfile.php URL.

    Example:
        https://uclass.uos.ac.kr/pluginfile.php/12345/mod_resource/content/3/lec01.pdf?forcedownload=1
        → "lec01.pdf"

    Returns None when the URL doesn't end in a recognizable filename (path
    has no extension on the last segment, or href is empty)."""
    if not href:
        return None
    try:
        path = urlparse(href).path
    except Exception:
        return None
    if not path:
        return None
    last = path.rstrip("/").rsplit("/", 1)[-1]
    if not last:
        return None
    name = unquote(last)
    if "." not in name:
        # Last segment looks like an itemid, not a filename — bail.
        return None
    # Reject server scripts that look like filenames (view.php etc.).
    if name.lower().endswith((".php", ".aspx", ".jsp", ".html", ".htm")):
        return None
    return name
