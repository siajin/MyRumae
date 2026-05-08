---
description: Quick read-only summary of lms.db — row counts per table, latest sync per course, top file types.
---

# /db-inspect — DB 상태 점검

읽기 전용. 현재 SQLite DB 가 채워진 상황을 한눈에 본다.

## 실행

```powershell
cd backend
python -c "
from app.db.database import SessionLocal
from app.db.models import Course, Assignment, Notice, Material, Summary
from sqlalchemy import func
db = SessionLocal()
try:
    print('--- Row counts ---')
    for M in (Course, Assignment, Notice, Material, Summary):
        print(f'  {M.__tablename__:12} = {db.query(M).count()}')
    print()
    print('--- Last synced per course ---')
    for c in db.query(Course).order_by(Course.last_synced_at.desc().nullslast()).all():
        print(f'  [{c.id}] {c.course_name[:30]:30} synced={c.last_synced_at}')
    print()
    print('--- Top 10 file types ---')
    rows = db.query(Material.file_type, func.count(Material.id)).group_by(Material.file_type).order_by(func.count(Material.id).desc()).limit(10).all()
    for ft, n in rows:
        print(f'  {ft or \"(none)\":10} = {n}')
finally:
    db.close()
"
```

## 보고

- `materials = 0` → 수집이 한 번도 성공 못함. `/smoke-collect 0`
- `summaries = 0` 인데 materials > 0 → AI 요약 미연결 (의도적일 수 있음)
- 특정 강좌의 `last_synced_at` 만 한참 오래됨 → 해당 강좌만 실패 중. `sync-doctor` 호출

## 하지 말 것
- 이 커맨드로 쓰기 작업 (UPDATE/INSERT) 추가하지 말 것 — 읽기 전용 유지
- DB 경로 하드코딩 — `app.db.database` 의 engine 만 사용
