// Mirrors the JSON Lines envelope emitted by backend/app/events.py.
// Every line on the Python worker's stdout becomes one SyncEvent.
export type SyncEvent = {
  type: string;
  ts: string;
  level: 'info' | 'warn' | 'error' | string;
  payload: Record<string, unknown>;
};

export type WorkerExit = {
  run_id: string;
  code: number;
};
