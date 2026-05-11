import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type { SyncEvent, WorkerExit } from './events';

export type StatusDto = { running: boolean; run_id: string | null };

export const startSync  = (): Promise<string>     => invoke<string>('start_sync');
export const cancelSync = (): Promise<void>       => invoke<void>('cancel_sync');
export const getStatus  = (): Promise<StatusDto>  => invoke<StatusDto>('get_status');
export const resetDb    = (): Promise<string>     => invoke<string>('reset_db');

export const onSyncEvent = (cb: (e: SyncEvent) => void): Promise<UnlistenFn> =>
  listen<SyncEvent>('sync-event', e => cb(e.payload));

export const onWorkerExit = (cb: (e: WorkerExit) => void): Promise<UnlistenFn> =>
  listen<WorkerExit>('worker-exit', e => cb(e.payload));
