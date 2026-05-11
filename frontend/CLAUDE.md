# frontend — Svelte 5 + Vite + TypeScript

MyRumae 데스크톱 앱의 UI 레이어. Tauri 셸([../src-tauri/](../src-tauri/))이 호스트한다. 백엔드(Python)와 직접 통신하지 않는다 — 항상 Rust를 경유.

루트 [CLAUDE.md](../CLAUDE.md) 도 함께 보아라.

---

## 1. 레이아웃

| 파일 | 책임 |
|---|---|
| `index.html` | Vite 엔트리. `<div id="app">` 하나. |
| `src/main.ts` | `mount(App, { target })` — Svelte 5 mount API (Svelte 4의 `new App({...})` 아님). |
| `src/App.svelte` | 유일한 컴포넌트. 상태 라벨 + Sync/Cancel 버튼 + 이벤트 로그. |
| `src/app.css` | 전역 스타일. 폰트는 `맑은 고딕` 우선. |
| `src/lib/ipc.ts` | **모든 `invoke` / `listen` 호출의 단일 진입점.** 컴포넌트에서 `@tauri-apps/api`를 직접 import 하지 말 것. |
| `src/lib/events.ts` | `SyncEvent`, `WorkerExit` 타입. backend/app/events.py 봉투와 1:1. |

---

## 2. 핵심 수칙

1. **Svelte 5 runes 전용.** `$state` / `$derived` / `$effect` / `$props` 만 사용. `let x = 0` 식 reactivity, `export let prop`, `$: ` reactive statement 모두 금지(legacy). props는 `let { foo, bar } = $props()`.
2. **`onclick` (소문자) 이벤트 어트리뷰트.** Svelte 5는 `on:click` 대신 `onclick={handler}` 사용. 신규 이벤트 어트리뷰트 모두 동일.
3. **IPC 경계는 `lib/ipc.ts` 한 곳.** 컴포넌트 → `ipc.ts` 래퍼 함수만 호출. `invoke`/`listen` import 금지. 새 invoke 커맨드를 Rust 측에서 추가하면 **반드시** `ipc.ts`에 동일한 이름의 wrapper와 TS 타입을 추가한다.
4. **이벤트 타입은 `events.ts` 단일 정의.** Rust → Svelte로 흐르는 `sync-event` payload 모양이 바뀌면 (= backend `events.py`가 바뀌면) 이 파일을 먼저 갱신한다. 모양이 안 맞으면 `payload`를 `unknown`으로 다루며 런타임 가드.
5. **상태 머신은 단순.** `'idle' | 'syncing' | 'done' | 'error'` 4개. `run_started` → `syncing`, `run_done`(payload.errors 보고 분기) → `done`/`error`, `error` 이벤트 → `error`. 이 외 이벤트는 로그 누적만.
6. **언리슨너 정리 필수.** `onSyncEvent`/`onWorkerExit`는 `Promise<UnlistenFn>` 반환. `onMount`의 cleanup에서 호출해 누수 방지.

---

## 3. 통신 흐름 한눈에

```
[App.svelte] 사용자 클릭
  ↓ ipc.startSync()
[Rust] commands::start_sync → worker::spawn_subcommand("sync")
  ↓ stdin/stdout/stderr piped
[Python] python -m app.cli sync → events.emit(...) 라인들
  ↓ stdout
[Rust] forward_stdout → app.emit("sync-event", json)
  ↓ Tauri event bus
[App.svelte] onSyncEvent 콜백 → $state 갱신 → DOM 재렌더
```

종료:
```
child exit → Rust app.emit("worker-exit", { run_id, code })
            → state.worker = None
[App.svelte] onWorkerExit 콜백 → 비정상 code면 status='error'
```

취소:
```
[App.svelte] ipc.cancelSync()
  ↓ Rust commands::cancel_sync → stdin.write_all(b"cancel\n")
[Python] cli.py stdin watcher → sync_task.cancel()
  → emit("run_done", { cancelled: true }) → 자연 종료
```

---

## 4. 빌드 / 개발

`frontend/` 에서:

```powershell
npm install              # 최초 1회
npm run dev              # Vite 단독 (브라우저로 확인, IPC 호출은 실패)
npm run tauri dev        # Tauri 셸과 함께 (실제 테스트 경로)
npm run check            # svelte-check 타입 검사
npm run build            # 정적 빌드 (dist/)
```

> `npm run tauri dev`가 자동으로 `npm run dev`를 띄운다 (tauri.conf.json `beforeDevCommand`).

---

## 5. 명시적 비포함 (다음 마일스톤)

- 강좌 목록/카드 UI.
- 진행률 바, ETA, 강좌별 progress.
- 로그인 입력 모달 (현재는 백엔드 `allow_manual_login=False`로 fail-fast).
- `regen-docx`/`parse`/`timetable`/`status` 버튼.
- 다국어, 다크/라이트 토글, 설정 화면.
- 라우팅 — 단일 페이지로 충분.
