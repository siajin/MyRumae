"""저장된 상태를 초기화한다.

기본: keyring + state.json 만 삭제 (안전)
--db: lms.db 까지 삭제
--files: data/raw 다운로드 파일까지 삭제
--all: 위 모두

사용 예:
    python scripts/reset.py            # keyring + state.json
    python scripts/reset.py --all      # 전부 초기화
"""
from __future__ import annotations

import argparse
import shutil
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


def reset_db() -> None:
    db_path = Path("data/lms.db")
    if db_path.exists():
        db_path.unlink()
        print(f"  DB: 삭제 완료 ({db_path})")
    else:
        print("  DB: 파일 없음")


def reset_files() -> None:
    # 1) backend/data/temp staging
    temp = Path("data") / "temp"
    if temp.exists():
        shutil.rmtree(temp)
        print(f"  파일: 삭제 완료 ({temp})")
    else:
        print(f"  파일: {temp} 없음")

    # 2) Desktop/UOS_LMS_AI user-facing tree
    from app.downloader.paths import desktop_root
    desk = desktop_root()
    if desk.exists():
        shutil.rmtree(desk)
        print(f"  파일: 삭제 완료 ({desk})")
    else:
        print(f"  파일: {desk} 없음")

    # 3) legacy backend/data/raw (pre-Desktop layout)
    legacy = Path("data") / "raw"
    if legacy.exists():
        shutil.rmtree(legacy)
        print(f"  파일: 삭제 완료 ({legacy}, legacy)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="lms.db도 삭제")
    ap.add_argument("--files", action="store_true", help="data/raw, data/temp도 삭제")
    ap.add_argument("--all", action="store_true", help="모두 삭제")
    args = ap.parse_args()

    print("초기화 시작:")
    reset_keyring()
    reset_state()
    if args.db or args.all:
        reset_db()
    if args.files or args.all:
        reset_files()
    print("완료.")


if __name__ == "__main__":
    main()
