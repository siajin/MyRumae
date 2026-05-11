"""DB · 캐시 · (옵션) 다운로드 트리를 초기화한다. 로그인은 절대 건드리지 않는다.

기본: lms.db (+ WAL/SHM) + data/user/parsed + data/user/temp + .master_apply.json
--files 옵션: Desktop/UOS_LMS_AI 트리도 삭제

로그인 (keyring + state.json) 은 scripts/reset.py 가 담당.
마스터 카탈로그 (data/master/) 는 어떤 옵션으로도 안 건드림.

사용:
    python scripts/reset_db.py            # DB + 캐시만
    python scripts/reset_db.py --files    # + Desktop 트리

Tauri 워커가 `python -m app.cli reset-db [--files]` 로 동일한 로직을 호출한다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_USER_DIR = _BACKEND_ROOT / "data" / "user"


def _unlink_with_retry(p: Path, attempts: int = 5, delay_s: float = 0.2) -> bool:
    """Windows briefly holds a handle after SQLAlchemy engine.dispose(); poll."""
    for i in range(attempts):
        try:
            p.unlink()
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay_s)
    return False


def reset_db() -> list[Path]:
    """Delete lms.db + WAL/SHM sidecars. Returns paths actually removed."""
    removed: list[Path] = []
    db_path = _USER_DIR / "lms.db"
    if db_path.exists() and _unlink_with_retry(db_path):
        removed.append(db_path)
    for sidecar in (db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")):
        if sidecar.exists() and _unlink_with_retry(sidecar):
            removed.append(sidecar)
    return removed


def reset_caches() -> list[Path]:
    """Wipe parsed/, temp/, raw(legacy)/ and the .master_apply.json marker.

    These caches are tightly coupled to DB rows (Material.id ↔ parsed/<id>.json).
    Resetting DB without these leaves dangling files; always clear together.
    """
    removed: list[Path] = []
    for sub in ("temp", "parsed", "raw"):
        t = _USER_DIR / sub
        if t.exists():
            shutil.rmtree(t)
            removed.append(t)
    marker = _USER_DIR / ".master_apply.json"
    if marker.exists():
        marker.unlink()
        removed.append(marker)
    return removed


def reset_desktop_tree() -> Path | None:
    """Optional: nuke Desktop/UOS_LMS_AI/. Returns path if deleted, else None."""
    from app.downloader.paths import desktop_root  # noqa: PLC0415 (lazy import)

    desk = desktop_root()
    if desk.exists():
        shutil.rmtree(desk)
        return desk
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--files",
        action="store_true",
        help="Desktop/UOS_LMS_AI 트리도 삭제",
    )
    args = ap.parse_args()

    print("DB · 캐시 초기화 (로그인 보존):")
    db_removed = reset_db()
    if db_removed:
        for p in db_removed:
            print(f"  DB: 삭제 완료 ({p})")
    else:
        print("  DB: 파일 없음")

    cache_removed = reset_caches()
    if cache_removed:
        for p in cache_removed:
            print(f"  캐시: 삭제 완료 ({p})")
    else:
        print("  캐시: 비어있음")

    if args.files:
        desk = reset_desktop_tree()
        if desk is not None:
            print(f"  파일: 삭제 완료 ({desk})")
        else:
            print("  파일: Desktop 트리 없음")

    print("완료.")


if __name__ == "__main__":
    main()
