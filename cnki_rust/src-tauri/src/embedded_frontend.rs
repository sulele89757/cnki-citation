//! 手动嵌入前端资源（绕过 tauri-build 不打包 frontendDist 的 bug）
//!
//! tauri-build / cargo-tauri build 均未能将 frontend/ 下的文件打入二进制
//! （已验证：exe 中找不到 index.html/app.js/styles.css 的任何唯一字符串）。
//! 本模块用 include_bytes! 直接把前端文件编进 .rs，再通过自定义协议提供。

pub const INDEX_HTML: &[u8] = include_bytes!("../../frontend/index.html");
pub const APP_JS: &[u8]     = include_bytes!("../../frontend/app.js");
pub const STYLES_CSS: &[u8] = include_bytes!("../../frontend/styles.css");
pub const DIALOG_JS: &[u8]  = include_bytes!("../../frontend/tauri-dialog.js");

/// 根据请求路径返回对应的嵌入内容；未命中返回 None。
pub fn get_asset(path: &str) -> Option<(&'static [u8], &'static str)> {
    let path = path.trim_start_matches('/').trim_start_matches('\\');
    match path {
        "" | "index.html" => Some((INDEX_HTML, "text/html; charset=utf-8")),
        "app.js"          => Some((APP_JS, "application/javascript; charset=utf-8")),
        "styles.css"      => Some((STYLES_CSS, "text/css; charset=utf-8")),
        "tauri-dialog.js" => Some((DIALOG_JS, "application/javascript; charset=utf-8")),
        _                 => None,
    }
}
