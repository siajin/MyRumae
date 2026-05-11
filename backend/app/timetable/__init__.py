"""Phase 1.5: Timetable + 강의계획서 enrichment from bundled master JSON.

Public entry: `refresh_timetable(allow_manual=False)` (async). Reads
`backend/data/master/courses_2026_1.json` (shipped with the app, updated
via app-store releases) and applies timetable slots / professor /
weekly-topic data to every `Course` row. No LMS login, no scraping.

Auto-called at the end of `scheduler.full_sync()`. A skip marker under
`backend/data/user/.master_apply.json` lets repeated syncs short-circuit
when neither the master file nor the user's course list has changed.
"""
from __future__ import annotations

import logging

from . import catalog  # noqa: F401  (re-export for callers)

from .runner import refresh_timetable  # noqa: F401

log = logging.getLogger(__name__)
