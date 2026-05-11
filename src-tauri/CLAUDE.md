# src-tauri — Tauri 2 트레이 셸 (Rust)

이 디렉터리는 MyRumae의 데스크톱 셸이다. 사용자에게 직접 보이는 진입점이며, 백엔드(Python) CLI를 spawn해서 LMS 동기화를 돌리고, 그 결과를 프론트엔드(Svelte)로 전달한다.

루트 [CLAUDE.md](../CLAUDE.md) 도 함께 보아라.

---

## 1. 모듈 구조

| 파일 | 책임 |
|---|---|
| `src/main.rs` | `tauri::Builder` 조립 — `manage(AppState)`, 플러그인, `invoke_handler`, `setup`(트레이 생성), `run`. |
| `src/state.rs` | `AppState { worker: Mutex<Option<WorkerHandle>> }`. `WorkerHandle`은 `run_id` + `stdin`(cancel용). |
| `src/worker.rs` | Python CLI subprocess: `spawn_subcommand("sync")` → tokio `Command::new(python).args(["-m","app.cli", subcmd])`. stdout JSON Lines 파서, stderr → tracing, stdin write → cancel, child wait → `worker-exit` 이벤트. |
| `src/commands.rs` | `#[tauri::command]` 3개: `start_sync` / `cancel_sync` / `get_status`. 트레이에서도 호출하는 헬퍼 `try_start_sync_from_tray`. |
| `src/tray.rs` | `TrayIconBuilder`, 메뉴(`동기화` / `메인 창 열기` / `종료`), 좌클릭은 main window 토글. |
| `Cargo.toml` | tauri 2 + tokio + serde + tracing + uuid. `tray-icon` feature 활성. |
| `tauri.conf.json` | `productName: MyRumae`, `identifier: kr.ac.uos.myrumae`, main 창 `visible:false`(트레이가 진입점), dev URL/port 1420. |
| `capabilities/default.json` | Tauri 2 권한 모델. `core:tray`, `core:menu`, `core:event`, `core:window`, `core:webview`, `core:app` 권한. |

---

## 2. 핵심 계약 (절대 깨지 말 것)

1. **stdout = 이벤트 채널.** Python 워커의 stdout에 들어오는 모든 라인은 한 줄에 하나의 JSON 봉투 `{"type","ts","level","payload"}`다. `worker.rs::forward_stdout`이 `serde_json::from_str` → `app.emit("sync-event", value)`로 그대로 전달. **백엔드 어느 모듈도 `print()` 금지 — 로깅은 stderr(`logging`)만**. (루트 CLAUDE.md §2-9 재명시)
2. **stdin = 취소 신호 채널.** `cancel_sync` 커맨드는 worker 핸들의 stdin에 `b"cancel\n"`을 쓴다. `cli.py`의 stdin watcher가 이를 받아 graceful 종료. 직접 `child.kill()`을 호출하지 말 것.
3. **WorkerHandle 라이프사이클.** `start_sync`는 이미 worker가 있으면 `Err("already running")`. wait task가 child 종료 시 `AppState::worker`를 `None`으로 클리어. 동일 run_id 확인 후에만 클리어(다음 worker를 덮어쓰지 않도록).
4. **Python 경로 해결 순서.** `MYRUMAE_PYTHON` env → `backend/.venv/Scripts/python.exe` → 리포 루트 `.venv/Scripts/python.exe` → PATH `python`. **이 순서를 바꾸면 사용자 환경의 venv를 우회한다.**
5. **Backend dir 해결.** `MYRUMAE_BACKEND_DIR` env → dev 기본값 `CARGO_MANIFEST_DIR/../backend`. 번들 모드는 향후 작업.
6. **Windows 콘솔 창 숨김.** GUI 앱이 Python을 spawn할 때 검은 콘솔이 깜빡이지 않도록 `creation_flags(CREATE_NO_WINDOW = 0x0800_0000)`. 다른 subprocess 추가 시도 동일 패턴.
7. **트레이는 메인 진입.** `tauri.conf.json` main window `visible:false`. 좌클릭으로 토글, 우클릭으로 메뉴. 메인창을 항상 띄우고 싶다면 conf의 visible을 바꾸지 말고 트레이 핸들러로 show.

---

## 3. 이벤트 카탈로그 (프론트와 1:1)

| 채널 | 페이로드 | 발신 시점 |
|---|---|---|
| `sync-event` | 백엔드 events.py 봉투 전체 (`type`/`ts`/`level`/`payload`) | Python stdout 라인 하나당 1회 |
| `worker-exit` | `{ run_id, code }` | child process가 종료된 직후 (정상/에러 무관) |

`type` 값 종류는 [backend/app/events.py](../backend/app/events.py) 가 SSOT. `run_started` / `run_done` / `login_*` / `course_*` / `docx_written` / `status` / `error` / `raw-line`(JSON 파싱 실패 라인).

---

## 4. 새 invoke 커맨드 추가 절차

1. `worker.rs`에 spawn 함수 추가 (필요 시 — sync 외 다른 cli 서브커맨드는 `spawn_subcommand("regen-docx")` 식으로 재사용 가능).
2. `commands.rs`에 `#[tauri::command]` 함수 작성. 항상 `Result<T, String>` 반환 (TS 측에서 try/catch).
3. `main.rs`의 `generate_handler![...]` 에 등록.
4. `capabilities/default.json` permissions에 추가 필요한 권한이 있는지 점검 (대부분 core 권한으로 충분).
5. **`frontend/src/lib/ipc.ts`에 동일한 이름의 wrapper 추가** — 1:1 매핑. Svelte 컴포넌트가 `invoke('...')`를 직접 호출하지 않도록.

---

## 5. 디버깅 팁

- Rust 로그는 stderr로 흐른다. `RUST_LOG=myrumae=debug,tauri=info npm run tauri dev` 식으로 필터링.
- Python 워커의 stderr는 `tracing::debug!`로 흘러간다. dev 콘솔에 보고 싶으면 `RUST_LOG=myrumae::worker::stderr=debug`.
- JSON Lines가 깨졌다면 → 백엔드 어딘가에 `print()`가 새로 생겼다는 신호. `forward_stdout`이 `raw-line` 이벤트로 래핑해 보내주므로 프론트에서도 확인 가능.
- 트레이 아이콘이 안 보이면: `tauri.conf.json` `bundle.icon`에 ICO/PNG가 모두 있는지, `app.default_window_icon()`이 `Some`을 돌려주는지 확인.

---

## 6. 명시적 비포함 (다음 마일스톤)

- `regen-docx` / `parse` / `timetable` / `status` 의 UI 노출.
- 강좌 목록 IPC (`list_courses` 등 read-only invoke).
- SSO 로그인 창의 Tauri 임베드.
- 번들/MSI/서명/자동 업데이트.
- PyInstaller sidecar (`bundle.externalBin`).
- DevTools 비활성, CSP 강화.
