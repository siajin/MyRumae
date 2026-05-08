# MyRumae — Claude Code Harness 개요

이 디렉토리(`.claude/`)와 리포 곳곳의 `CLAUDE.md` 들이 합쳐져서 본 프로젝트의 **Claude Code 하네스**를 이룬다. 사람이 읽는 README가 아니라 **Claude Code가 자동으로 로드/호출하는 설정 묶음**이다.

## 1. 어떻게 동작하는가

### 자동 로드 (passive)
Claude Code 가 세션 시작 시, 그리고 디렉토리에 들어갈 때마다 가장 가까운 `CLAUDE.md`들을 컨텍스트에 올린다.

```
c:/MyRumae/CLAUDE.md                          ← 항상 로드
c:/MyRumae/backend/CLAUDE.md                  ← backend/ 안에서 작업할 때
c:/MyRumae/backend/app/auth/CLAUDE.md         ← auth 코드 만질 때
c:/MyRumae/backend/app/collector/CLAUDE.md    ← collector 코드 만질 때
c:/MyRumae/backend/app/db/CLAUDE.md           ← db 모델/쿼리 만질 때
c:/MyRumae/backend/app/downloader/CLAUDE.md   ← 다운로드 로직 만질 때
c:/MyRumae/backend/app/docs/CLAUDE.md         ← DOCX 작성 만질 때
c:/MyRumae/backend/app/scheduler/CLAUDE.md    ← 스케줄러 만질 때
```

규칙: 짧게, 실행에 직결된 정보만, 추상 아키텍처보다 "한 번 깨졌던 함정" 우선.

### 수동 호출 (active)

| 형태 | 호출 방법 | 어디 |
|---|---|---|
| 슬래시 커맨드 | 사용자가 `/sync` 등 입력 | `.claude/commands/*.md` |
| 서브에이전트 | Claude 가 Agent tool 로 위임 | `.claude/agents/*.md` |

## 2. 파일 인벤토리

### CLAUDE.md (모듈 컨텍스트)

| 경로 | 다루는 것 |
|---|---|
| [/CLAUDE.md](../CLAUDE.md) | 프로젝트 전체 한 장 요약 + 실행 명령 + 핵심 도메인 지식 |
| [backend/CLAUDE.md](../backend/CLAUDE.md) | 백엔드 셋업, 16개 실전 함정 (실제로 한 번씩 깨졌던 것들) |
| [backend/app/auth/CLAUDE.md](../backend/app/auth/CLAUDE.md) | 로그인 우선순위 (state.json → keyring → manual), SSO 함정 |
| [backend/app/collector/CLAUDE.md](../backend/app/collector/CLAUDE.md) | 셀렉터 SSOT, snapshot 패턴, modtype 추가 절차 |
| [backend/app/db/CLAUDE.md](../backend/app/db/CLAUDE.md) | 모델 unique key, upsert 패턴, 마이그레이션(없음) 절차 |
| [backend/app/downloader/CLAUDE.md](../backend/app/downloader/CLAUDE.md) | sha256 dedupe 시퀀스, 경로 규약, cross-volume `shutil.move` |
| [backend/app/docs/CLAUDE.md](../backend/app/docs/CLAUDE.md) | DOCX 섹션 구조, 한글 폰트, AI 요약 wiring |
| [backend/app/scheduler/CLAUDE.md](../backend/app/scheduler/CLAUDE.md) | full_sync 흐름, lock/coalesce 보호, 환경변수 |

### 서브에이전트 (`.claude/agents/`)

| 에이전트 | 언제 부르나 |
|---|---|
| [selector-debugger](agents/selector-debugger.md) | Playwright 가 0건 반환 / stale element / UCLASS UI 변경 의심 |
| [schema-migrator](agents/schema-migrator.md) | `models.py` 수정 — 컬럼/테이블/유니크 변경 |
| [smoke-runner](agents/smoke-runner.md) | "어느 smoke 부터 돌릴지" 의사결정 + 실패 트리아지 |
| [docx-tuner](agents/docx-tuner.md) | DOCX 섹션/스타일 변경 + AI 요약 통합 |
| [sync-doctor](agents/sync-doctor.md) | full_sync 가 부분/전체 실패할 때 단계별 진단 |

### 슬래시 커맨드 (`.claude/commands/`)

| 커맨드 | 무엇을 하나 |
|---|---|
| [/sync](commands/sync.md) | 한 번만 full_sync 실행 (스케줄러 안 띄우고) |
| [/smoke-collect](commands/smoke-collect.md) | 한 강좌 활동 목록(또는 실수집) 빠른 점검 |
| [/login](commands/login.md) | 로그인 + state.json/keyring 갱신 |
| [/reset](commands/reset.md) | 단계적 상태 초기화 (기본은 keyring + state.json) |
| [/docs](commands/docs.md) | LMS 미접속 상태로 DOCX 정리노트 재생성 |
| [/selector-check](commands/selector-check.md) | 저장된 HTML 샘플 4개로 셀렉터 드리프트 점검 |
| [/db-inspect](commands/db-inspect.md) | lms.db 행수/마지막 sync/파일타입 통계 (읽기전용) |

## 3. 레이어드 디자인

```
┌────────────────────────────────────────────┐
│  사용자 의도 (자연어)                        │
└────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│  슬래시 커맨드  (.claude/commands/*.md)      │  ← 자주 쓰는 사용자 액션
│  /sync, /login, /reset, /docs ...           │
└────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│  서브에이전트  (.claude/agents/*.md)         │  ← 진단/위임이 필요한 작업
│  selector-debugger, schema-migrator, ...    │
└────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│  CLAUDE.md  (root + 모듈별)                  │  ← 항상 컨텍스트로 깔리는 규칙
│  도메인지식 + 실전 함정 + 코드 스타일         │
└────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│  코드 (backend/app/...)                     │  ← 실제 구현
└────────────────────────────────────────────┘
```

## 4. 추가/변경 가이드

### 새 함정을 알게 됐을 때
→ `backend/CLAUDE.md` (전역) 또는 해당 모듈의 `CLAUDE.md`(국소) "주의사항"에 한 항목 추가. 실제 깨졌던 사례 1줄 + 패턴 1줄.

### 새 작업 흐름이 반복될 때
→ `.claude/commands/<name>.md` 추가. frontmatter `description` + `argument-hint` 필수.

### 작업 흐름이 진단/판단을 요할 때 (단순 명령 아님)
→ `.claude/agents/<name>.md` 추가. `tools:` 는 최소권한(읽기/검색만) 부터 시작.

### 새 modtype / 새 외부 시스템 연동
→ 코드 추가 + 해당 모듈 `CLAUDE.md` 갱신 + (영구적인 액션이면) 슬래시 커맨드 추가.

## 5. 의도적으로 두지 않은 것

- **`.claude/settings.json`** — hook/permission 자동화는 아직 도입 안 함. 추가 필요 시 `update-config` 스킬로.
- **CI 워크플로우** — 본 프로젝트는 로컬 에이전트라 CI 없음.
- **테스트 디렉토리 가이드** — 정식 unit test 없음 (smoke 스크립트로 대체). pytest 도입 시 `backend/tests/CLAUDE.md` 신설.
- **Alembic 마이그레이션 가이드** — 도입 시 `backend/migrations/CLAUDE.md` 신설하고 `db/CLAUDE.md` "스키마 변경" 섹션 갱신.

## 6. 사용 예시

```
사용자: "강좌 목록은 잘 나오는데 공지가 0건이야"
→ Claude 는 collector/CLAUDE.md 와 backend/CLAUDE.md §10 (selector 검증 범위)을
  컨텍스트로 읽고, /selector-check 또는 selector-debugger 에이전트를 띄움.

사용자: "Material 에 mime_type 컬럼 추가하고 싶어"
→ Claude 는 db/CLAUDE.md (upsert 패턴) 컨텍스트 + schema-migrator 에이전트 호출.
  reset 절차와 데이터 보존 여부를 사용자에게 묻고 진행.

사용자: "/sync"
→ commands/sync.md 의 PowerShell one-liner 실행.
  결과 dict 의 errors > 0 이면 sync-doctor 에이전트로 자동 트리아지.
```
