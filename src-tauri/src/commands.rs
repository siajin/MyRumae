use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::state::AppState;
use crate::worker;

#[derive(Serialize)]
pub struct StatusDto {
    pub running: bool,
    pub run_id: Option<String>,
}

#[tauri::command]
pub async fn start_sync(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<String, String> {
    {
        let guard = state.worker.lock().await;
        if guard.is_some() {
            return Err("already running".into());
        }
    }
    worker::spawn_subcommand(app, "sync", &[])
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn cancel_sync(app: AppHandle) -> Result<(), String> {
    worker::write_cancel(&app).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_status(state: State<'_, AppState>) -> Result<StatusDto, String> {
    let guard = state.worker.lock().await;
    Ok(StatusDto {
        running: guard.is_some(),
        run_id: guard.as_ref().map(|h| h.run_id.clone()),
    })
}

/// Wipe DB + caches + (always) the Desktop download tree. Preserves login.
/// Mutually exclusive with sync — both share the single WorkerHandle slot.
#[tauri::command]
pub async fn reset_db(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<String, String> {
    {
        let guard = state.worker.lock().await;
        if guard.is_some() {
            return Err("already running".into());
        }
    }
    worker::spawn_subcommand(app, "reset-db", &["--files"])
        .await
        .map_err(|e| e.to_string())
}

pub async fn try_start_sync_from_tray(app: &AppHandle) {
    let state = app.state::<AppState>();
    {
        let guard = state.worker.lock().await;
        if guard.is_some() {
            tracing::info!("tray sync click ignored — worker already running");
            return;
        }
    }
    match worker::spawn_subcommand(app.clone(), "sync", &[]).await {
        Ok(run_id) => tracing::info!(run_id = %run_id, "tray-triggered sync started"),
        Err(e) => tracing::error!(error = %e, "tray-triggered sync failed to start"),
    }
}
