//! CNKI 论文引文获取工具 —— Tauri v2 入口
//!
//! 复用 `cnki_citation_rs` 库（抓取引擎）作为后端，前端为 WebView2 中的 Web UI。
//! - 单例：tauri-plugin-single-instance（第二实例仅激活已有窗口）
//! - 系统托盘：tray.rs（显示窗口 / 退出，左键恢复）
//! - 关闭主窗口 → 仅隐藏到托盘（不退出），与 Python 版行为一致
//!
//! 前端资源通过 `embedded_frontend` (include_bytes!) 直接嵌入二进制，
//! 再用自定义 URI scheme `cnki` 提供（Windows 上即 http://cnki.localhost/）。
//! 规避 tauri-build 未能把 frontendDist 文件打入二进制的坑。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod embedded_frontend;
mod tray;

use tauri::{window::Color, Manager, WindowEvent};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            // 单例锁：第二实例激活已有窗口
            tauri_plugin_single_instance::init(|app, _argv, _cwd| {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.unminimize();
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            }),
        )
        // 注册自定义协议：提供手动嵌入的前端资源
        .register_uri_scheme_protocol("cnki", move |_ctx, request| {
            let path = request.uri().path();
            match embedded_frontend::get_asset(path) {
                Some((data, mime)) => tauri::http::Response::builder()
                    .status(200)
                    .header("Content-Type", mime)
                    .body(data.to_vec())
                    .unwrap(),
                None => tauri::http::Response::builder()
                    .status(404)
                    .body(b"Not found".to_vec())
                    .unwrap(),
            }
        })
        .setup(|app| {
            // 系统托盘（显示窗口 / 退出），左键恢复
            if let Err(e) = tray::create_tray(app.handle()) {
                eprintln!("[托盘] 创建失败：{e}");
            }
            // 主窗口关闭 → 最小化到托盘（不退出）
            // Tauri 2.x：用 on_window_event + WindowEvent::CloseRequested{api} 拦截
            if let Some(w) = app.get_webview_window("main") {
                // 强制用自定义协议加载前端（不依赖 tauri-build 的资产打包）
                let _ = w.navigate(tauri::Url::parse("http://cnki.localhost/index.html").unwrap());

                let wc = w.clone();
                w.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = wc.hide();
                    }
                });

                // 窗口在配置里是 visible:false —— 先按系统主题着色再显示，
                // 避免亮色用户先看到一帧暗色（或反之）。
                let theme = commands::system_theme(app.handle().clone());
                let bg = if theme == "light" {
                    Color(255, 255, 255, 255)
                } else {
                    Color(15, 17, 23, 255)
                };
                let _ = w.set_background_color(Some(bg));
                let _ = w.show();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::start_single,
            commands::start_batch,
            commands::check_update,
            commands::perform_update,
            commands::show_browser,
            commands::history_count,
            commands::clean_history,
            commands::download_template,
            commands::open_path,
            commands::open_output,
            commands::get_version,
            commands::system_theme,
            commands::default_save_dir,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
