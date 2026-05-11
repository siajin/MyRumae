use tauri::{
    menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

use crate::commands;

pub fn build(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let sync_item = MenuItem::with_id(app, "sync", "동기화", true, None::<&str>)?;
    let open_item = MenuItem::with_id(app, "open", "메인 창 열기", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&sync_item, &open_item, &sep, &quit_item])?;

    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or("default window icon is not set in tauri.conf.json bundle.icon")?;

    let _tray = TrayIconBuilder::with_id("main-tray")
        .tooltip("MyRumae")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .icon(icon)
        .on_menu_event(|app, event| on_menu(app, event))
        .on_tray_icon_event(|tray, event| {
            on_tray_icon(tray.app_handle(), event);
        })
        .build(app)?;

    Ok(())
}

fn on_menu(app: &AppHandle, event: MenuEvent) {
    match event.id.as_ref() {
        "sync" => {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move {
                commands::try_start_sync_from_tray(&handle).await;
            });
        }
        "open" => show_main_window(app),
        "quit" => app.exit(0),
        other => {
            tracing::warn!(menu_id = %other, "unknown tray menu id");
        }
    }
}

fn on_tray_icon(app: &AppHandle, event: TrayIconEvent) {
    if let TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        toggle_main_window(app);
    }
}

fn show_main_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

fn toggle_main_window(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    match win.is_visible() {
        Ok(true) => {
            let _ = win.hide();
        }
        _ => {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}
