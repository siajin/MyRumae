<script lang="ts">
  import { onMount } from 'svelte';
  import { startSync, cancelSync, getStatus, resetDb, onSyncEvent, onWorkerExit } from './lib/ipc';
  import type { SyncEvent } from './lib/events';

  type Status = 'idle' | 'syncing' | 'done' | 'error';

  let status = $state<Status>('idle');
  let lastEvent = $state<SyncEvent | null>(null);
  let log = $state<SyncEvent[]>([]);
  let errorMessage = $state<string | null>(null);

  const label = $derived(
    status === 'syncing'
      ? `Syncing… (${lastEvent?.type ?? '...'})`
      : status,
  );

  onMount(() => {
    let unlistenSync: (() => void) | undefined;
    let unlistenExit: (() => void) | undefined;

    // Recover state on (re)mount — if a sync is already running on the Rust side
    // (e.g. user just hit 재로드 mid-sync), reflect it in the label.
    getStatus()
      .then((s) => {
        if (s.running) status = 'syncing';
      })
      .catch(() => {
        /* outside Tauri webview — leave status='idle' */
      });

    onSyncEvent((ev) => {
      log = [...log.slice(-99), ev];
      lastEvent = ev;
      if (ev.type === 'run_started') {
        status = 'syncing';
        errorMessage = null;
      } else if (ev.type === 'run_done') {
        const errs = (ev.payload as { errors?: number })?.errors ?? 0;
        status = errs > 0 ? 'error' : 'done';
      } else if (ev.type === 'error') {
        status = 'error';
        errorMessage = String((ev.payload as { message?: unknown })?.message ?? 'error');
      } else if (ev.type === 'login_failed') {
        status = 'error';
        errorMessage = String((ev.payload as { reason?: unknown })?.reason ?? 'login failed');
      }
    }).then((u) => (unlistenSync = u));

    onWorkerExit((ev) => {
      if (ev.code !== 0 && status === 'syncing') {
        status = 'error';
        errorMessage = errorMessage ?? `worker exited with code ${ev.code}`;
      }
    }).then((u) => (unlistenExit = u));

    return () => {
      unlistenSync?.();
      unlistenExit?.();
    };
  });

  async function onSyncClick() {
    errorMessage = null;
    try {
      await startSync();
    } catch (e) {
      status = 'error';
      errorMessage = String(e);
    }
  }

  async function onCancelClick() {
    try {
      await cancelSync();
    } catch (e) {
      errorMessage = String(e);
    }
  }

  function onReloadClick() {
    // Full webview reload: re-runs main.ts → onMount → re-subscribes to events
    // and re-queries getStatus, so the UI re-converges on the Rust truth.
    window.location.reload();
  }

  async function onResetDbClick() {
    const ok = window.confirm(
      "DB와 다운로드된 파일을 모두 삭제합니다.\n" +
        "로그인 상태(state.json, keyring)는 그대로 유지됩니다.\n\n" +
        "계속하시겠습니까?",
    );
    if (!ok) return;
    errorMessage = null;
    try {
      await resetDb();
    } catch (e) {
      status = 'error';
      errorMessage = String(e);
    }
  }
</script>

<main>
  <h1>MyRumae</h1>
  <p>
    Status:
    <strong class="status-{status}">{label}</strong>
  </p>

  {#if errorMessage}
    <p class="status-error">⚠ {errorMessage}</p>
  {/if}

  <div>
    <button onclick={onSyncClick} disabled={status === 'syncing'}>Sync now</button>
    <button onclick={onCancelClick} disabled={status !== 'syncing'}>Cancel</button>
    <button onclick={onReloadClick} title="UI 재로드 (Rust 측 상태 다시 동기화)">재로드</button>
    <button
      onclick={onResetDbClick}
      disabled={status === 'syncing'}
      title="DB · 캐시 · Desktop 트리 삭제 (로그인 보존)"
    >DB 리셋</button>
  </div>

  <pre>{log.slice(-12).map((e) => `${e.ts}  ${e.type}`).join('\n') || '(no events yet)'}</pre>
</main>
