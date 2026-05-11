// MyRumae — Tauri 2 tray shell entry point.
// stdout from the spawned Python worker is JSON Lines (see backend/app/events.py);
// each line is forwarded verbatim as a "sync-event" Tauri event to the frontend.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod state;
mod tray;
mod worker;

use tracing_subscriber::EnvFilter;

fn main() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,myrumae=debug"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_writer(std::io::stderr)
        .init();

    tauri::Builder::default()
        .manage(state::AppState::default())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            commands::start_sync,
            commands::cancel_sync,
            commands::get_status,
            commands::reset_db,
        ])
        .setup(|app| {
            tray::build(app.handle())?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build tauri app")
        .run(|_app, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                // Future milestone: gracefully cancel a running worker before exit.
            }
        });
}
