---
description: Run smoke_collect.py against one course. Defaults to --dry-run (list activities only).
argument-hint: [course-index] [--full]
---

# /smoke-collect — Single-course collector smoke test

한 강좌만 골라 활동 목록을 보거나(--dry-run) 실수집까지 돌린다(--full).

## 인자 해석
- 첫 번째 인자: 강좌 인덱스 (정수, 기본 0). 사이드바 dropdown 순서.
- `--full` 이 포함되면 실수집(다운로드 + DB 쓰기). 없으면 dry-run.

## 실행

```powershell
cd backend
# dry-run 기본
python scripts/smoke_collect.py --course-index $ARG_INDEX --dry-run

# --full 인자 시
python scripts/smoke_collect.py --course-index $ARG_INDEX
```

## 보고

- dry-run: `cmid / modtype / section_idx` 표가 출력되면 OK
- full: 마지막 줄 `결과: {'folder': X, 'ubboard': Y, 'assign': Z, 'skipped': W, 'downloaded': N}` — `downloaded` 가 0인지/양수인지 사용자에게 알림

## 실패 시 다음 단계 안내
- `is_logged_in` False → `/reset` + `python scripts/smoke_login_headed.py`
- `0 activities` → `selector-debugger` 에이전트 호출
- 다운로드 timeout → `LOG_LEVEL=DEBUG` 로 재실행하고 `sync-doctor` 호출
