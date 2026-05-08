---
description: Run a one-shot full LMS sync (login → courses → materials → DOCX). For ad-hoc runs outside the scheduler.
argument-hint: [--manual]
---

# /sync — One-shot full sync

스케줄러를 띄우지 않고 `full_sync`만 한 번 실행한다.

```powershell
cd backend
python -c "import asyncio; from app.db.init_db import init_db; from app.scheduler.jobs import full_sync; init_db(); print(asyncio.run(full_sync(allow_manual_login=$ARGUMENTS_MANUAL_BOOL)))"
```

`$ARGUMENTS`에 `--manual`이 포함되어 있으면 `allow_manual_login=True`(첫 실행/state 만료 시 prompt 허용), 아니면 `False`(스케줄러와 동일 모드).

## 실행 후 확인 포인트
- 반환 dict의 `errors` 가 0인지
- `Desktop/UOS_LMS_AI/<강좌>/<N주차>/원본/`에 새 파일이 생겼는지
- `정리/` 폴더의 DOCX 가 갱신됐는지 (`mtime` 확인)

## 안전
- 사용자가 명시적으로 `/sync`를 호출했을 때만 실행. 다른 명령 결과로 자동 트리거하지 말 것.
- `--manual` 없이 시작했는데 `LoginError` 가 뜨면 사용자에게 `/sync --manual` 또는 `python scripts/smoke_login_headed.py` 안내.
