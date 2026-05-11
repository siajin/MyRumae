"""Stdout JSON Lines event emitter for the Tauri worker bridge.

The Tauri (Rust) shell spawns `python -m app.cli <subcommand>` and reads
stdout line-by-line. Every line MUST be exactly one JSON object with this
envelope:

    {"type": "<event>", "ts": "<iso8601 utc>", "level": "info|warn|error",
     "payload": { ... }}

Rules:
- All other modules log via the `logging` package (stderr). Never print()
  to stdout from anywhere else — a single stray line corrupts the stream.
- emit() is the only writer to stdout. It flushes immediately so Rust sees
  progress in real time.
- Events are silently dropped when MYRUMAE_EVENTS=off (e.g. when smoke
  scripts are run interactively and stdout is a TTY for humans).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


_DISABLED = os.environ.get("MYRUMAE_EVENTS", "on").lower() in ("0", "off", "false")


def _iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(type: str, *, level: str = "info", **payload: Any) -> None:
    """Write one envelope to stdout as a single JSON line + flush."""
    if _DISABLED:
        return
    line = json.dumps(
        {"type": type, "ts": _iso_utc(), "level": level, "payload": payload},
        ensure_ascii=False,
        default=str,
    )
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def heartbeat() -> None:
    emit("heartbeat")
