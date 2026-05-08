# MyRumae — Claude Code Project Guide

서울시립대학교(UOS) UCLASS LMS 전용 **로컬 학업관리 에이전트**.
Playwright로 LMS를 주기적으로 크롤링 → SQLite에 메타 저장 → Desktop 폴더에 자료 다운로드 + DOCX 정리노트 생성.

이 파일은 Claude Code가 자동으로 모든 세션에 로드합니다. 짧고 실행에 직결된 정보만 둡니다.

---

## 1. 한눈에 보는 아키텍처

```
사용자 PC
└── backend/  (Python, FastAPI 예정)
    ├── app/
    │   ├── main.py           ← 진입점: init_db → full_sync → 30분 주기 스케줄
    │   ├── selectors.py      ← UCLASS DOM 셀렉터 단일 진실원(SSOT)
    │   ├── auth/             ← 로그인 (state.json + keyring + 수동 fallback)
    │   ├── collector/        ← 강좌/공지/자료실/과제 스크레이퍼 (Playwright async)
    │   ├── downloader/       ← 첨부파일 다운로드 + SHA256 dedupe
    │   ├── db/               ← SQLAlchemy 모델 + repository
    │   ├── docs/             ← python-docx 로 정리.docx 생성
    │   └── scheduler/        ← APScheduler full_sync 잡
    ├── scripts/              ← smoke_login, smoke_collect, smoke_docs, reset
    ├── data/lms.db           ← SQLite (gitignored)
    └── playwright-state/state.json   ← 로그인 세션 (gitignored)
```

데이터 흐름: `LMS 페이지 → collector(Playwright) → repository(SQLAlchemy) → SQLite`
파일 흐름: `LMS 첨부 → downloader(temp) → SHA256 dedupe → Desktop/UOS_LMS_AI/<과목>/<N>주차/원본/`

---

## 2. 필수 수칙 (코드 작성 전 반드시 확인)

1. **DOM 셀렉터는 절대 인라인으로 박지 말 것.** 모두 [backend/app/selectors.py](backend/app/selectors.py) 한 파일에서 관리. UCLASS UI가 바뀌면 이 파일만 수정.
2. **자격증명은 평문 저장 금지.** `keyring`(OS 보안 저장소)만 사용. [backend/app/auth/credentials.py](backend/app/auth/credentials.py) 참조.
3. **로그인 우선순위 = state.json → keyring → 수동 prompt.** 스케줄러 잡은 `allow_manual_login=False`. [backend/app/auth/login.py](backend/app/auth/login.py)의 `ensure_logged_in` 변경 시 이 순서 유지.
4. **다운로드는 SHA256 중복 검사 후 저장.** [backend/app/downloader/download.py](backend/app/downloader/download.py)의 `download_via_click` 패턴 우회 금지.
5. **사용자 노출 산출물은 DOCX**. 마크다운 원문은 내부 저장만(`Summary.summary_md`). 사용자에게 보여주려면 `app.docs.docx_writer`를 통해 변환.
6. **경로는 `Path(__file__)` 기반 절대경로.** CWD 의존 코드를 새로 만들지 말 것 — 스케줄러가 어디서 실행되든 같은 DB/파일을 보아야 함.
7. **윈도우 환경**. `shutil.move` 사용(크로스볼륨), 파일명은 [paths.sanitize_segment](backend/app/downloader/paths.py)로 정제.
8. **Korean fonts in DOCX**: `맑은 고딕`. [docx_writer._set_korean_default_font](backend/app/docs/docx_writer.py)에서 강제.

---

## 3. 자주 쓰는 명령

PowerShell 기준, `backend/`에서 실행:

```powershell
# 1회 로그인 (창 띄우고, SSO/2FA 통과)
python scripts/smoke_login_headed.py

# 헤드리스 로그인 점검
python scripts/smoke_login.py

# 한 강좌만 수집해보기
python scripts/smoke_collect.py --course-index 0 --dry-run
python scripts/smoke_collect.py --course-index 0

# DB → DOCX 재생성 (LMS 미접속)
python scripts/smoke_docs.py
python scripts/smoke_docs.py --course 1

# 상태 초기화 (단계적)
python scripts/reset.py            # keyring + state.json
python scripts/reset.py --db       # + lms.db
python scripts/reset.py --all      # + 다운로드 파일

# 본 진입점 (init_db → full_sync → 스케줄 시작)
python -m app.main
```

환경변수:
- `LOG_LEVEL=DEBUG|INFO|WARNING`
- `SYNC_INTERVAL_MINUTES=30` (기본 30)
- `UCLASS_HEADLESS=0` 으로 두면 collector가 창 띄움
- `DROP_AND_RECREATE=1` 로 두면 `init_db()`가 모든 테이블 drop 후 재생성

---

## 4. UCLASS 도메인 지식 (코드만 읽으면 모르는 것)

- **로그인 페이지가 SSO 리디렉션을 자주 함.** `ensure_logged_in`은 navigation interrupt를 정상 흐름으로 간주하고, 끝에 `is_logged_in()`으로 한 번 더 검증.
- **`/my/` 대시보드 사이드바의 `li.dropdown-item-course[data-courseid]`** 가 수강 강좌 목록의 SSOT. 강좌 페이지 좌측 메뉴는 사용하지 않음.
- **강좌 페이지는 `?mode=sections` 로 평탄화** 해서 한 번에 모든 활동을 볼 수 있게 한다. [course_page.collect_course_materials](backend/app/collector/course_page.py).
- **활동 종류(modtype)** 는 4종만 처리: `folder`(자료실), `ubboard`(공지/게시판), `assign`(과제), `resource`(스킵). 새 modtype은 [selectors.KNOWN_MODTYPES](backend/app/selectors.py) 에 추가.
- **게시판 글 ID = `bwid` (URL 쿼리스트링).** cmid + bwid 조합이 `Notice` 테이블의 unique key.
- **과제 마감일 라벨**: 한국어 "마감/종료" 또는 영어 "Due"가 든 `<td.cell.c0>`을 찾고 다음 형제 `<td>`에서 값 추출.
- **샘플 HTML이 리포 루트에 있음** (`강좌_*.html`, `홈 _*.html` 등). 셀렉터 점검 시 이 파일들로 오프라인 검증.

---

## 5. 데이터 모델 (단축 요약)

[backend/app/db/models.py](backend/app/db/models.py):

| 테이블 | unique key | 비고 |
|---|---|---|
| `courses` | `moodle_course_id` | LMS의 course id가 영구 키 |
| `assignments` | `(course_id, cmid)` | |
| `notices` | `(course_id, cmid, bwid)` | bwid 가 게시글 id |
| `materials` | `(course_id, sha256)` | sha256으로 강좌 내 중복 방지 |
| `summaries` | (material_id, latest) | material 1개당 1개 (덮어쓰기) |

스키마 변경 시: 모델 수정 → `DROP_AND_RECREATE=1 python -m app.db.init_db` (개발 단계에서 마이그레이션은 아직 도입 안 함).

---

## 6. 알려진 함정

- **Playwright Locator는 navigate 후 stale.** `course_page._snapshot_activities`처럼 `page.evaluate`로 한 번에 dict로 떠서 쓴다. 활동 순회 중 새로 locator로 다시 찾지 말 것.
- **`async with page.expect_navigation`** 안에서 click 한 뒤 timeout이 나도 정상일 수 있음(SSO chain). 끝에 url/DOM 검증으로 판단.
- **`shutil.move`** 만 사용. `Path.rename`은 temp(`backend/data/temp`)→Desktop 크로스볼륨에서 실패함.
- **`session.STATE_PATH`** 는 `backend/playwright-state/state.json`. 위치 변경 금지(스케줄러/스모크 모두 의존).
- **Windows에서 `signal.SIGTERM` 비지원.** [main._main_async](backend/app/main.py)는 try/except NotImplementedError 로 우회.

---

## 7. 하네스 엔지니어링 산출물 위치

- `.claude/HARNESS.md` — 본 하네스 셋업 개요/인덱스
- `.claude/agents/*.md` — 전문 에이전트 (셀렉터 디버거, 스키마 마이그레이터, 스모크 러너 등)
- `.claude/commands/*.md` — 슬래시 커맨드 (/sync, /smoke-collect, /reset, /docs 등)
- `backend/CLAUDE.md`, `backend/app/<sub>/CLAUDE.md` — 모듈별 짧은 가이드
