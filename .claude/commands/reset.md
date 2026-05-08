---
description: Reset persistent state. Default = keyring + state.json only. Pass --db / --files / --all for wider wipes.
argument-hint: [--db] [--files] [--all]
---

# /reset — 단계적 상태 초기화

`backend/scripts/reset.py`의 안전한 wrapper. 기본은 가장 좁은 범위(자격증명 + 세션)만 지운다.

## 단계

| 인자 | 지우는 것 | 사용 시점 |
|---|---|---|
| (없음) | keyring + state.json | "다른 계정으로 로그인하고 싶다" |
| `--db` | + lms.db | "스키마가 바뀌어서 충돌난다" |
| `--files` | + temp + Desktop/UOS_LMS_AI + legacy data/raw | "다운로드 결과를 통째로 다시 받고 싶다" |
| `--all` | 위 모두 | "처음부터" |

## 실행

```powershell
cd backend
python scripts/reset.py $ARGUMENTS
```

## 안전 (필수)

- `--db` 또는 `--files` 또는 `--all` 이 인자에 있으면 **사용자에게 즉시 확인 받기**. 데스크톱의 다운로드 파일과 SQLite DB를 영구 삭제한다.
- 자동 트리거 금지. 항상 사용자가 명시적으로 `/reset ...` 을 입력했을 때만 실행.
- 실행 직전에 `Desktop/UOS_LMS_AI` 가 비어있지 않다면 사용자에게 그 사실을 알리고 한 번 더 컨펌.

## 실행 후

`/login` → `/smoke-collect 0` 흐름으로 다시 셋업.
