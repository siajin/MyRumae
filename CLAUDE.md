# MyRumae — Claude Code Project Guide

서울시립대학교(UOS) UCLASS LMS 전용 **로컬 학업관리 에이전트**.
Playwright로 LMS를 주기적으로 크롤링 → SQLite에 메타 저장 → Desktop 폴더에 자료 다운로드 + DOCX 정리노트 생성.

이 파일은 Claude Code가 자동으로 모든 세션에 로드합니다. 짧고 실행에 직결된 정보만 둡니다.

---

## 1. 한눈에 보는 아키텍처

```
사용자 PC
├── backend/  (Python — Tauri 워커)
│   ├── app/
│   │   ├── cli.py           ← Tauri가 spawn하는 진입점 (sync/regen-docx/parse/status/timetable)
│   │   ├── events.py        ← stdout JSON Lines emit (Tauri 이벤트 브릿지)
│   │   ├── main.py          ← 레거시 단독 실행용 (init_db → full_sync → 스케줄). 신규 작업은 cli.py로.
│   │   ├── selectors.py     ← UCLASS DOM 셀렉터 단일 진실원(SSOT)
│   │   ├── auth/            ← 로그인 (state.json + keyring + 수동 fallback)
│   │   ├── collector/       ← 강좌/공지/자료실/과제 스크레이퍼 (Playwright async)
│   │   ├── downloader/      ← 첨부파일 다운로드 + SHA256 dedupe
│   │   ├── parser/          ← PDF 파싱(PyMuPDF) + OCR(PaddleOCR, lazy)
│   │   ├── db/              ← SQLAlchemy 모델 + repository (WAL 모드)
│   │   ├── docs/            ← python-docx 로 정리.docx 생성 (파싱 본문 포함)
│   │   ├── timetable/       ← master JSON → DB enrich (시간표/교수/주차 토픽)
│   │   └── scheduler/       ← APScheduler full_sync 잡 (앱 단독 실행 시에만 사용)
│   ├── scripts/             ← smoke_login, smoke_collect, smoke_docs, smoke_timetable, reset
│   ├── data/
│   │   ├── master/                ← 앱 번들 자산 (committed, 학기 전환 시 갱신)
│   │   │   └── courses_2026_1.json
│   │   └── user/                  ← 사용자 상태 (gitignored, 자동 생성)
│   │       ├── lms.db             ← SQLite (WAL)
│   │       ├── parsed/<id>.json   ← ParsedContent 블록 JSON
│   │       ├── temp/              ← 다운로드 staging
│   │       └── .master_apply.json ← 적용 스킵 마커 (mtime + course_count)
│   └── playwright-state/state.json   ← 로그인 세션 (gitignored)
├── src-tauri/  (Rust — Tauri 2 트레이 셸)
│   ├── Cargo.toml / build.rs / tauri.conf.json
│   ├── capabilities/default.json    ← Tauri 2 권한 모델 (트레이/창/이벤트)
│   ├── icons/                       ← 트레이/창 아이콘 (개발용 placeholder)
│   └── src/
│       ├── main.rs                  ← Builder + 플러그인/트레이/invoke 등록
│       ├── commands.rs              ← #[tauri::command] start_sync / cancel_sync / get_status
│       ├── worker.rs                ← Python CLI subprocess: spawn + JSON Lines stdout → app.emit("sync-event")
│       ├── tray.rs                  ← TrayIconBuilder + 메뉴 라우터 (동기화/창 열기/종료)
│       └── state.rs                 ← AppState { worker: Mutex<Option<WorkerHandle>> }
└── frontend/   (Svelte 5 + Vite + TypeScript)
    ├── package.json / vite.config.ts / svelte.config.js / tsconfig*.json
    ├── index.html
    └── src/
        ├── main.ts                  ← Svelte 5 mount(App)
        ├── App.svelte               ← 상태 라벨 + Sync/Cancel 버튼 (runes)
        ├── app.css
        └── lib/
            ├── ipc.ts               ← invoke / listen 단일 진입점
            └── events.ts            ← SyncEvent 타입 (events.py 봉투와 1:1)
```

데이터 흐름: `LMS 페이지 → collector(Playwright) → repository(SQLAlchemy) → SQLite (data/user/lms.db)`
파일 흐름: `LMS 첨부 → downloader(data/user/temp) → SHA256 dedupe → Desktop/UOS_LMS_AI/<과목>/<source_label>/원본/` (source_label = 활동 이름, 예: "강의자료실"/"공지사항"/"1주차 과제")
DOCX 흐름: 자료 1개당 정리 DOCX 1개. `Desktop/UOS_LMS_AI/<과목>/<source_label>/정리/<파일명>_정리.docx` + 공지/과제 각각도 별도 DOCX.
보강 흐름: `data/master/courses_*.json → timetable.apply_catalog_to_db → Course.professor + Timetable + CourseSyllabus`
UI 흐름: `사용자 트레이 클릭 → Svelte invoke('start_sync') → Rust worker.spawn → python -m app.cli sync → stdout JSON Lines → app.emit('sync-event') → Svelte $state 갱신`

---

## 2. 필수 수칙 (코드 작성 전 반드시 확인)

1. **DOM 셀렉터는 절대 인라인으로 박지 말 것.** 모두 [backend/app/selectors.py](backend/app/selectors.py) 한 파일에서 관리. UCLASS UI가 바뀌면 이 파일만 수정.
2. **자격증명은 평문 저장 금지.** `keyring`(OS 보안 저장소)만 사용. [backend/app/auth/credentials.py](backend/app/auth/credentials.py) 참조.
3. **로그인 우선순위 = state.json → keyring → 수동 prompt.** 스케줄러 잡은 `allow_manual_login=False`. [backend/app/auth/login.py](backend/app/auth/login.py)의 `ensure_logged_in` 변경 시 이 순서 유지.
4. **다운로드는 SHA256 중복 검사 후 저장.** [backend/app/downloader/download.py](backend/app/downloader/download.py)의 `download_via_click` 패턴 우회 금지.
5. **사용자 노출 산출물은 DOCX**. AI 요약은 현재 **비활성**(코드는 유지) — DOCX의 "파싱 본문" 섹션은 `ParsedContent`(PyMuPDF/OCR 결과) 만 채운다. `Summary` 모델/`upsert_summary`는 향후 AI 재활성화용으로 코드만 살려두고 호출 안 함.
6. **경로는 `Path(__file__)` 기반 절대경로.** CWD 의존 코드를 새로 만들지 말 것 — 스케줄러가 어디서 실행되든 같은 DB/파일을 보아야 함. 사용자 상태는 전부 `backend/data/user/`, 앱 번들 마스터 JSON은 `backend/data/master/` 안에만.
7. **윈도우 환경**. `shutil.move` 사용(크로스볼륨), 파일명은 [paths.sanitize_segment](backend/app/downloader/paths.py)로 정제.
8. **Korean fonts in DOCX**: `맑은 고딕`. [docx_writer._set_korean_default_font](backend/app/docs/docx_writer.py)에서 강제.
9. **stdout은 JSON Lines 전용.** `app.cli`의 어떤 코드도 다른 모듈이 `print()`로 stdout에 쓰면 Tauri 브릿지가 깨진다. 로깅은 항상 `logging`(stderr)을 통하라. emit은 [app.events](backend/app/events.py) 만.
10. **CLAUDE.md 동기화 의무.** 코드를 수정했을 때, 그 변경이 관련 CLAUDE.md(루트 [CLAUDE.md](CLAUDE.md), [backend/CLAUDE.md](backend/CLAUDE.md), 또는 모듈별 `backend/app/<sub>/CLAUDE.md`)에 적힌 내용과 어긋나면 **같은 작업 안에서 해당 CLAUDE.md도 함께 수정**한다. 어긋나는 항목 예: 디렉터리/파일 구조, 진입점·CLI 명령, 셀렉터 SSOT 위치, 모델 unique key, 환경변수, 로그인/다운로드 흐름, DOCX 산출 규칙, modtype 목록 등. 영향받는 CLAUDE.md가 없는지 먼저 확인하고, 있으면 코드 diff와 함께 문서 diff도 낸다. 단순 리팩터링·내부 변수명 변경처럼 문서에 영향 없는 변경은 제외.

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

# 상태 초기화 — 두 스크립트가 책임 분리
python scripts/reset.py            # 로그인만 (keyring + state.json)
python scripts/reset_db.py         # DB + 캐시 (로그인 보존)
python scripts/reset_db.py --files # + Desktop/UOS_LMS_AI 트리

# Tauri/사용자 진입점 (이게 우선) — 한 번의 동기화
python -m app.cli sync

# DB만으로 DOCX 재생성 (강좌 지정 가능)
python -m app.cli regen-docx
python -m app.cli regen-docx --course 1

# 단일 material 재파싱 / 강좌 단위 batch 재파싱
python -m app.cli parse --material 42
python -m app.cli parse --course 1

# DB + 캐시 리셋 (Tauri의 "DB 리셋" 버튼도 이걸 부른다)
python -m app.cli reset-db
python -m app.cli reset-db --files   # Desktop 트리도

# 한 줄 상태 (counts + state.json 위치)
python -m app.cli status

# 레거시 단독 진입점 (앱 없이 데몬처럼 굴리고 싶을 때)
python -m app.main
```

Tauri 셸 (**리포 루트** `c:\MyRumae\` 에서 실행, Rust 툴체인 + Node.js 필요):

```powershell
# 의존성 설치 (최초 1회) — frontend/에서
cd frontend
npm install
cd ..

# dev — 루트에서. Vite + Tauri 동시 기동, 트레이 아이콘 등장
npm run tauri dev   # 또는 npm run dev

# 정적 빌드 + 인스톨러
npm run tauri build

# (frontend 단독) 타입체크 / Vite만
npm --prefix frontend run check
npm --prefix frontend run build
```

> Tauri CLI는 `tauri.conf.json`을 CWD 하위에서만 찾으므로 **루트에서 실행**해야 한다. 루트 `package.json`이 `frontend/node_modules/.bin/tauri`로 위임한다.
> `cargo` / `rustc`가 PATH에 없으면 막힌다. `rustup default stable-msvc`로 설치.

환경변수:
- `LOG_LEVEL=DEBUG|INFO|WARNING`
- `SYNC_INTERVAL_MINUTES=30` (기본 30)
- `UCLASS_HEADLESS=0` 으로 두면 collector가 창 띄움
- `DROP_AND_RECREATE=1` 로 두면 `init_db()`가 모든 테이블 drop 후 재생성
- `MYRUMAE_PYTHON=<python.exe>` — Rust worker가 spawn할 Python 실행 파일 강제 지정. 미지정시 `backend/.venv/Scripts/python.exe` → 리포 루트 `.venv` → PATH `python` 순으로 fallback.
- `MYRUMAE_BACKEND_DIR=<path>` — backend 디렉터리 강제 지정. dev 기본값은 `src-tauri/../backend` (즉 리포 내부의 backend 폴더).

---

## 4. UCLASS 도메인 지식 (코드만 읽으면 모르는 것)

- **로그인 페이지가 SSO 리디렉션을 자주 함.** `ensure_logged_in`은 navigation interrupt를 정상 흐름으로 간주하고, 끝에 `is_logged_in()`으로 한 번 더 검증.
- **`/my/` 대시보드 사이드바의 `li.dropdown-item-course[data-courseid]`** 가 수강 강좌 목록의 SSOT. 강좌 페이지 좌측 메뉴는 사용하지 않음.
- **강좌 페이지는 `?mode=sections` 로 평탄화** 해서 한 번에 모든 활동을 볼 수 있게 한다. [course_page.collect_course_materials](backend/app/collector/course_page.py).
- **활동 종류(modtype)** 는 5종만 처리: `folder`(자료실 다파일), `ubboard`(공지/게시판), `ubfile`(주차별 단일파일 강의자료 — UCLASS 전용), `assign`(과제), `resource`(스킵). 새 modtype은 [selectors.KNOWN_MODTYPES](backend/app/selectors.py) 에 추가.
- **게시판 글 ID = `bwid` (URL 쿼리스트링).** cmid + bwid 조합이 `Notice` 테이블의 unique key.
- **과제 마감일 라벨**: 한국어 "마감/종료" 또는 영어 "Due"가 든 `<td.cell.c0>`을 찾고 다음 형제 `<td>`에서 값 추출.
- **샘플 HTML이 리포 루트에 있음** (`강좌_*.html`, `홈 _*.html` 등). 셀렉터 점검 시 이 파일들로 오프라인 검증.

---

## 5. 데이터 모델 (단축 요약)

[backend/app/db/models.py](backend/app/db/models.py):

| 테이블 | unique key | 비고 |
|---|---|---|
| `courses` | `moodle_course_id` | LMS의 course id가 영구 키 |
| `assignments` | `(course_id, cmid)` | `source_label` 컬럼 = 활동 이름 (정리/ 경로 키) |
| `notices` | `(course_id, cmid, bwid)` | bwid 가 게시글 id. `source_label` = 부모 게시판 이름 |
| `materials` | `(course_id, sha256)` | sha256으로 강좌 내 중복 방지. `parse_status` + `source_label` 컬럼 |
| `parsed_contents` | `material_id` | PDF/OCR 파싱 결과. 블록 JSON은 `backend/data/parsed/<id>.json` |
| `timetable_slots` | `(course_id, weekday, start_time)` | `data/master/courses_*.json` 에서 자동 채움 (full_sync 끝) |
| `course_syllabi` | `course_id` | `schedule_json` 주차별 토픽 (master 에서 채움). `pdf_path`/`parsed_text` 컬럼은 보존만 — `repo.upsert_syllabus` 시그니처도 받지 않음 |
| `summaries` | (material_id, latest) | AI 요약 — 현재 미사용, 향후 복구용 |

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
