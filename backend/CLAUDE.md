# backend/ — Module Guide

Python 백엔드. 진입점 `app/main.py`. 모든 스크립트는 **이 디렉토리에서** 실행한다 (`scripts/`가 `sys.path.insert(0, parent)`로 `app/`을 import).

## 실행 컨텍스트

```powershell
# 가상환경
..\\.venv\\Scripts\\Activate.ps1

# 의존성
pip install -r ..\\requirements.txt
playwright install chromium

# 본 실행
python -m app.main
```

## 폴더별 책임

| 디렉토리 | 책임 | 외부와의 접점 |
|---|---|---|
| `app/auth/` | 로그인 | OS keyring, `playwright-state/state.json` |
| `app/collector/` | LMS DOM 스크레이핑 | Playwright |
| `app/downloader/` | 파일 다운로드 + dedupe | Playwright `expect_download` |
| `app/parser/` | PDF/PPTX/DOCX 텍스트 추출 | PyMuPDF, PaddleOCR(lazy), python-pptx, python-docx |
| `app/db/` | SQLAlchemy 모델/리포지토리 | SQLite `data/user/lms.db` |
| `app/docs/` | DOCX 정리노트 생성 | python-docx |
| `app/timetable/` | master JSON → DB enrich (시간표/교수/주차 토픽) | `data/master/courses_*.json` |
| `app/scheduler/` | 주기적 full_sync | APScheduler |
| `app/cli.py` | Tauri 가 spawn 하는 CLI 진입점 | stdout JSON Lines |
| `app/events.py` | stdout 이벤트 emit | (Tauri 브릿지) |
| `scripts/` | 스모크 테스트 + 초기화 | CLI |

각 서브디렉토리에는 별도 `CLAUDE.md`가 있을 수 있음 — 해당 모듈을 수정할 때만 자동 로드된다.

## 신규 작업자 체크리스트

1. `python scripts/smoke_login_headed.py` 로 SSO 첫 통과 → state.json 생성
2. `python scripts/smoke_collect.py --course-index 0 --dry-run` 으로 강좌 목록 확인
3. `python scripts/smoke_collect.py --course-index 0` 로 한 강좌 실수집
4. `python scripts/smoke_timetable.py --dry-run` 으로 master JSON 매칭률 확인
5. `python -m app.cli regen-docx` 로 DOCX 생성 확인 (`smoke_docs.py` 는 deprecated)
6. 문제 발생 시 `python scripts/reset.py --all` 로 초기화 후 재시도

## 코드 스타일 핵심

- `from __future__ import annotations` 표준
- 비동기 함수는 `async def` (Playwright API가 async-only)
- 타입힌트 필수 (DTO는 `@dataclass`)
- 로깅은 `log = logging.getLogger(__name__)`, 레벨은 `LOG_LEVEL` env로 제어
- 예외는 모듈 단위로 좁게 catch — collector 한 활동 실패가 전체 sync를 죽이면 안 됨

---

# 주의사항 (실제로 한 번씩 다 깨졌던 것들)

## 1. 경로는 반드시 `backend/` 기준 절대경로로 anchor

CWD-relative 경로(`Path("playwright-state/state.json")`)는 같은 명령을 다른 폴더에서 실행하면 다른 파일을 가리킨다. 실제로 reset.py를 `C:\MyRumae\`에서, smoke_login.py를 `C:\MyRumae\backend\`에서 실행해서 reset이 아무것도 못 지운 사고가 있었음.

**규칙**: 새 파일/디렉토리 상수 만들 때 무조건 이 패턴.

```python
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
SOMETHING = _BACKEND_ROOT / "data" / "something"
```

이미 anchor된 곳: `app/auth/session.py` (`STATE_PATH`), `app/downloader/paths.py` (`TEMP_ROOT`, Desktop 경로), `app/db/database.py` (`DATABASE_URL`).

_(과거에 CWD-relative 였던 [scripts/reset.py](scripts/reset.py) 는 `_BACKEND_ROOT` anchor 로 전환됨 — 모든 운영 경로가 절대 경로.)_

## 2. UOS는 SSO(NTLM/Kerberos)로 자동 인증된다

학교 망/도메인 PC에서 `is_logged_in()`이 학번/비번 없이도 True를 반환하는 게 정상. `playwright.new_context()`로 fresh context를 만들어도 OS-level 인증은 막지 못한다. 이걸 "버그"로 오해하지 말 것.

부산물:
- `is_logged_in()`은 `wait_until="load"` + `wait_for_load_state("networkidle")` 둘 다 써야 한다. SSO redirect 체인(`/login/` → SSO 포털 → `/course/view.php?id=...`)이 끝날 때까지 기다리지 않으면 중간 상태에서 False를 잘못 반환함.
- `_login_with_credentials()`는 `goto(/login/)`이 redirect로 인해 interrupt되는 걸 정상 신호로 간주해야 함. try/except로 감싸고 그 후 `is_logged_in()` 재확인.
- 자격증명 prompt 직전에 한 번 더 `is_logged_in()` 체크 — prompt 대기 중에 SSO가 인증을 끝낼 수 있음.

SSO 끄고 싶으면: `chromium.launch(args=["--auth-server-allowlist=", "--auth-negotiate-delegate-allowlist="])`.

## 3. Playwright Locator는 페이지 이동 후 stale

`await page.locator(...).all()`은 lazy 핸들 — 평가 시점의 DOM을 본다. 활동 페이지로 navigate한 뒤 다시 그 Locator를 쓰면 아무것도 안 매칭된다.

**규칙**: navigation 전에 `page.evaluate()` 한 번으로 모든 메타데이터를 plain dict로 snapshot. [course_page.py:_snapshot_activities()](backend/app/collector/course_page.py)가 모범.

## 4. async vs sync Playwright

`AsyncIOScheduler` + `async_playwright`만 쓴다. `sync_playwright`는 FastAPI/APScheduler가 가진 이벤트 루프와 충돌. 새 collector 만들 때 동기 버전 절대 추가하지 말 것.

`scheduler/jobs.py`의 모듈 레벨 `asyncio.Lock`은 overlapping sync 방지용 — 제거 금지.

## 5. dedupe 키는 sha256, URL 절대 금지

Moodle `pluginfile.php` URL은 itemid가 회전한다. 같은 PDF를 재업로드하면 URL은 바뀌고 내용은 같음 → URL 기반 dedupe는 깨진다. `Material.UniqueConstraint(course_id, sha256)` 유지 필수.

## 6. modtype 분기는 folder/ubboard/ubfile/assign 4종

UOS는 `modtype_resource`를 안 쓴다 (실제 강좌 샘플에 0개). 파일은 다음 4개 안에 있음:
- `modtype_folder` — 자료실(다파일)
- `modtype_ubboard` — 공지/Q&A 게시판 + 첨부
- `modtype_ubfile` — UCLASS 전용 단일 파일 활동 (주차별 강의자료/슬라이드를 1파일=1활동 으로 올릴 때)
- `modtype_assign` — 과제 + 첨부

`resource` 분기 추가하지 말 것 — 검증 없이 추가하면 dead code. 새 modtype 발견 시 샘플 HTML 확보 후 [collector/CLAUDE.md](app/collector/CLAUDE.md) 절차에 따라 추가.

## 7. cross-volume 파일 이동은 `shutil.move` 필수

`backend/data/temp` (C:\)에서 `Desktop/UOS_LMS_AI` (D:\일 수 있음 — Windows 폴더 리다이렉션)로 이동할 때 `Path.rename()`은 cross-volume에서 실패한다. 이미 [download.py:87](backend/app/downloader/download.py#L87)이 `shutil.move`로 처리. 새 다운로드 로직 짤 때 같은 패턴.

## 8. collector 파라미터는 `course_name` (not `course_code`)

Desktop 폴더 구조가 `<강좌명>/<N>주차/원본/`인데 강좌명은 `course_code`(40121_01_U) 대신 `course_name`(C프로그래밍, 한글)을 쓴다. 모든 collector 함수 시그니처가 통일됨 — 새 collector도 `course_name: str`만 받기.

## 9. 사용자 노출 파일 vs 내부 데이터

| 위치 | 용도 | 누가 봄 |
|---|---|---|
| `backend/data/master/courses_*.json` | 학기 전체 강좌 universe (앱 번들, committed) | 시스템만 — 앱 업데이트로만 갱신 |
| `backend/data/user/lms.db` | 메타데이터 + dedupe + Summary markdown | 시스템만 |
| `backend/data/user/temp/` | 다운로드 중 staging | 시스템만 (자동 정리) |
| `backend/data/user/parsed/<id>.json` | PDF 파싱 블록 JSON | 시스템만 |
| `backend/data/user/.master_apply.json` | 마스터→DB 적용 스킵 마커 | 시스템만 |
| `backend/data/user/raw/` | legacy 다운로드 (pre-Desktop 잔재, 신규 코드 미사용) | 시스템만 — `reset.py --files` 로만 정리 |
| `~/Desktop/UOS_LMS_AI/<강좌>/<source_label>/원본/` | 다운로드 원본 (source_label = 활동 이름) | 사용자 |
| `~/Desktop/UOS_LMS_AI/<강좌>/<source_label>/정리/` | 자료/공지/과제 1개당 DOCX 1개 | 사용자 |

원칙: **`master/` 는 read-only (앱이 직접 쓰지 않음), `user/` 는 모두 read-write.** `reset.py` 는 어떤 옵션으로도 `master/` 를 건드리지 않는다.

## 10. selector는 4개 페이지에서만 검증됨

레포 루트의 4개 HTML 샘플(로그인/홈/강좌/공지목록)에서만 selector가 확정됐다. 아직 검증되지 않은 추측 selector:

- `BOARD.ARTICLE_TITLE / ARTICLE_AUTHOR / ARTICLE_POSTED_AT / ARTICLE_BODY` — 공지 본문 페이지 샘플 없음
- `ASSIGN.DUE_AT_ROW_LABEL / VALUE / DESCRIPTION` — Moodle 기본값 추측
- `FOLDER.DOWNLOAD_FOLDER_BTN` — 폴더 zip 다운로드 fallback (실제 동작 미검증)

selector 수정할 때는 `--headed`로 실 페이지 확인 → [selectors.py](backend/app/selectors.py) 한 곳에서만 수정. 코드 곳곳에 selector 하드코딩 절대 금지.

## 11. DB 스키마 변경 시

Alembic 없음. `models.py` 수정 후:

```powershell
$env:DROP_AND_RECREATE="1"; python -m app.db.init_db
```

기존 데이터 전부 날아간다. 처음 실데이터가 들어가는 시점에 Alembic 도입 예정.

## 12. SQLAlchemy 2.x deprecation 주의

`db.query(Model).get(pk)`는 deprecated. 새 코드는 `db.get(Model, pk)` 사용. [repository.py:50](backend/app/db/repository.py#L50) `mark_course_synced`가 아직 옛날 스타일 — 동작은 하지만 경고 뜸.

## 13. 한글/특수문자 파일명 안전화

Windows path-illegal chars (`< > : " / \ | ? *` + 0x00-0x1f) 제거. 무조건 [paths.sanitize_segment()](backend/app/downloader/paths.py#L30) 통과시키기. 직접 문자열 조작 금지.

## 14. keyring 두 단계 저장

[credentials.py](backend/app/auth/credentials.py)는 `(SERVICE, "_username_")` → 활성 username, `(SERVICE, username)` → password 형식. 단일 키로 합치지 말 것 — Windows credential manager는 (service, username) pair가 키이기 때문에 username을 모르면 password를 못 찾음.

## 15. headless가 기본, headed는 디버깅용

- `smoke_login.py` — headless 기본 사용
- `smoke_login_headed.py` — 창 표시. SSO 캡차/2FA 통과, selector 검증, DOM 직접 확인용
- 환경변수 `UCLASS_HEADLESS=0`도 동일 효과 ([browser.py:18](backend/app/collector/browser.py#L18))

운영 코드는 항상 headless 가정으로 짠다 — `expect_dialog` / 사용자 클릭 가정 금지.

## 16. 한 활동 실패가 전체를 죽이지 않게

[course_page.py:134](backend/app/collector/course_page.py#L134)처럼 활동 단위로 try/except. 한 modtype 페이지 selector가 깨져도 다른 modtype은 계속 수집되어야 함. `db.commit()`을 활동 단위로 자주 부르는 이유도 같음 — 중간에 죽어도 앞부분은 살아남음.
