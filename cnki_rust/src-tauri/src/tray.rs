//! 系统托盘：显示窗口 / 退出，左键恢复主窗口。关闭主窗口时由 main.rs 改为隐藏，托盘常驻。

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

/// 创建系统托盘（含右键菜单：显示窗口 / 退出）。
pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let show_item = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

    // 托盘图标：编译期解码内嵌 PNG（Tauri 2.x 用 include_image!，Image::from_bytes 已移除）
    // 注意：该宏的路径基准是 CARGO_MANIFEST_DIR（即 src-tauri/），不是当前源文件目录。
    let icon = tauri::include_image!("icons/icon.png");

    TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => restore(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button, .. } = event {
                // 仅左键恢复窗口；右键由 .menu() 自动弹出菜单
                if button == MouseButton::Left {
                    restore(tray.app_handle());
                }
            }
        })
        .build(app)?;

    Ok(())
}

/// 恢复主窗口并置顶。
fn restore(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}
