# app/scheduler — Periodic Sync

APScheduler `AsyncIOScheduler` + `IntervalTrigger`. 단 하나의 잡: `full_sync`.

## full_sync 흐름

[`jobs.full_sync(*, allow_manual_login=False)`](jobs.py):

```
asyncio.Lock() 획득
  └── browser_session() (Playwright)
        ├── auth.ensure_logged_in(allow_manual=False)   ← 실패 시 errors+=1, 종료
        ├── courses.collect_courses(page) → CourseDTO[]
        ├── 각 강좌마다:
        │     ├── repo.upsert_course + commit
        │     ├── course_page.collect_course_materials  ← 활동 순회
        │     ├── docs.generate_course_summaries        ← DOCX 재생성
        │     └── repo.mark_course_synced + commit
        └── session.save_state()  ← state.json 갱신
```

## 절대 깨면 안 되는 것

- **`asyncio.Lock` 보호**: 스케줄 간격이 짧을 때 겹치는 실행을 막는다. `max_instances=1, coalesce=True` + lock 이중 안전망.
- **수동 로그인 비활성**: 백그라운드 잡이라 `allow_manual_login=False`. CLI에서 사용자 입력 받는 path가 살아나면 silently 멈춤.
- **강좌 한 개 실패가 전체 실패가 아님**: 강좌 단위 try/except. errors 카운트만 올리고 계속 진행.
- **DB 세션 lifecycle**: `try/finally db.close()` 패턴 유지. 강좌 단위 commit — 도중에 실패해도 이전 강좌 결과는 보존.

## 환경변수

| 이름 | 기본 | 의미 |
|---|---|---|
| `SYNC_INTERVAL_MINUTES` | 30 | 잡 주기 |
| `LOG_LEVEL` | INFO | 모듈 전체 로깅 |
| `UCLASS_HEADLESS` | 1 | 0이면 창 띄움 (디버그용) |

## 변경 가이드

- 잡을 추가하려면 새 함수를 정의하고 `start_scheduler` 안에서 `sched.add_job(...)` 추가. ID 충돌 주의 (`lms_full_sync`).
- 잡 외부에서 `full_sync`를 직접 await할 수 있음 (예: `main.py` 초기 1회 실행). 그 경우에도 lock 으로 안전.
- 종료 신호: `asyncio.get_running_loop().add_signal_handler(SIGINT/SIGTERM, ...)`. Windows에서는 `NotImplementedError`라 silent fallback.
