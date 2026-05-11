"""저장된 로그인 상태를 초기화한다 (keyring + state.json).

DB/캐시/다운로드 파일은 건드리지 않는다 — 그건 scripts/reset_db.py 가 담당.
마스터 카탈로그(backend/data/master/) 도 어떤 옵션으로도 삭제하지 않는다.

사용 (어느 CWD 에서 실행해도 동일):
    python scripts/reset.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import credentials, session  # noqa: E402


def reset_keyring() -> None:
    creds = credentials.load_credentials()
    if creds is None:
        print("  keyring: 저장된 자격증명 없음")
        return
    credentials.delete_credentials()
    print(f"  keyring: 삭제 완료 ({creds[0]})")


def reset_state() -> None:
    if session.STATE_PATH.exists():
        session.STATE_PATH.unlink()
        print(f"  state.json: 삭제 완료 ({session.STATE_PATH})")
    else:
        print("  state.json: 파일 없음")


def main() -> None:
    print("로그인 상태 초기화 (DB/파일은 scripts/reset_db.py 사용):")
    reset_keyring()
    reset_state()
    print("완료.")


if __name__ == "__main__":
    main()
