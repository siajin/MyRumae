# app/db — Persistence Layer

SQLAlchemy 1.x 동기 ORM + SQLite. 마이그레이션 도구는 아직 없음(개발 단계).

## 파일

- `database.py` — `engine`, `SessionLocal`, `Base`. DB 위치는 `backend/data/user/lms.db` (절대경로). import 시점에 `_migrate_legacy_layout()` 가 구 위치(`data/lms.db`, `data/parsed/`, `data/temp/`, `data/courses_2026_1.json`) 를 새 master/user 트리로 1회 이동.
- `models.py` — 8개 테이블: `Course`, `Assignment`, `Notice`, `Material`, `Summary`(미사용·보존), `ParsedContent`, `Timetable`, `CourseSyllabus`. **`Material`/`Notice`/`Assignment` 모두 `source_label` 컬럼을 가진다** — Desktop 경로/DOCX 그룹화의 키. 활동 이름(`div.activityname`/`data-activityname`)에서 채워진다.
- `repository.py` — upsert/조회 함수. **모든 DB 쓰기는 여기 통과.**
- `init_db.py` — `Base.metadata.create_all`. `DROP_AND_RECREATE=1` 환경변수 시 drop 후 재생성.

## Material.parse_status 상태머신

`pending → running → done | failed | skipped`. PDF/PPTX/DOCX 는 `done` 까지 가고 (parser/pdf.py + parser/office.py 분기), `_SKIP_EXTS`(zip/hwp/xlsx 등) 만 `skipped`. `done` 이외 상태도 DOCX "파싱 본문" 에 해당 사유가 그대로 노출됨.

## 핵심 unique key

```
courses(moodle_course_id) UNIQUE
assignments(course_id, cmid) UNIQUE
notices(course_id, cmid, bwid) UNIQUE
materials(course_id, sha256) UNIQUE   ← 같은 강좌 내 중복 다운로드 방지
parsed_contents(material_id) UNIQUE
timetable_slots(course_id, weekday, start_time) UNIQUE
course_syllabi(course_id) UNIQUE
summaries: material_id 당 1행 (덮어쓰기 패턴, 현재 미사용)
```

## upsert 패턴 (반드시 따를 것)

```python
def upsert_X(db, *, key1, key2, ...):
    row = db.query(X).filter(X.key1 == key1, X.key2 == key2).one_or_none()
    if row is None:
        row = X(key1=key1, key2=key2)
        db.add(row)
    row.field_a = ...
    row.field_b = ...
    db.flush()
    return row
```

호출자가 `db.commit()`을 책임진다. repository는 `flush`만 한다.

## 스키마 변경

지금은 마이그레이션 없음 — 모델만 고치면 기존 DB와 어긋난다.

```powershell
# 가장 안전한 진행
python scripts/reset.py --db
DROP_AND_RECREATE=1 python -m app.db.init_db
```

향후 alembic 도입 시 이 문서 업데이트할 것.

## DateTime 규약

- 모두 **naive UTC** (`datetime.utcnow()` 또는 파싱된 naive 값). timezone-aware 섞지 말 것.
- 게시 시각/마감 시각은 UCLASS가 KST로 표기 — 파서에서 그대로 datetime 객체로 받는다 (변환 없이).
- `fetched_at`만 `utcnow()`. 비교 시 둘 다 naive 라는 가정.

## 새 테이블 추가 체크리스트

1. [models.py](models.py)에 `class X(Base)` + `__table_args__` UniqueConstraint
2. [repository.py](repository.py)에 `upsert_X` / 조회 함수
3. 호출 측에서 `repo.upsert_X(db, ...); db.commit()` 패턴 사용
4. `DROP_AND_RECREATE=1`로 DB 재생성, smoke 스크립트 통과 확인
