//! Tauri IPC 命令：把已有的 Rust 抓取引擎桥接到前端 Web UI。

use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, Theme};

use cnki_citation_rs::browser::{self, RunOpts};
use cnki_citation_rs::config;
use cnki_citation_rs::update::Updater;

/// Gitee 更新检测配置（与 Python 版一致；该 token 仅只读权限，可打包进 exe）。
const GITEE_OWNER: &str = "sulele";
const GITEE_REPO: &str = "cnki-citation";
const GITEE_TOKEN: &str = "7fdea635702f2c7d1005de1620476aa1";

/// 本工具（Rust 版）可执行文件名，用于自更新时定位临时文件与旧 exe。
const APP_NAME: &str = "CNKICitationTool-rs";

/// 并发守卫：避免同一时刻重复启动抓取任务。
static RUNNING: Mutex<bool> = Mutex::new(false);

// ── DTO（用于把引擎结果序列化给前端）──
#[derive(Serialize, Clone)]
pub struct RecordDto {
    pub title: String,
    pub citation: Option<String>,
    pub success: bool,
    pub skipped: bool,
    pub error: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct TaskResult {
    pub mode: String,
    pub records: Vec<RecordDto>,
}

/// 更新信息 DTO。
/// 注意：引擎侧的 `UpdateInfo` 未 derive `Serialize`（不满足 Tauri 的 IpcResponse），
/// 故在此做一层可序列化的镜像，避免改动上游库。
#[derive(Serialize, Clone, Default)]
pub struct UpdateInfoDto {
    pub has_update: bool,
    pub latest: String,
    pub url: String,
    pub notes: String,
    pub download_url: String,
}

// ════════════════════════════════════════════
//  抓取任务（单篇 / 批量）
// ════════════════════════════════════════════
#[tauri::command]
pub fn start_single(
    app: AppHandle,
    title: String,
    human: bool,
    min_gap: f64,
    max_gap: f64,
) -> Result<(), String> {
    run_task(
        app,
        vec![title],
        None,
        "single".into(),
        human,
        min_gap,
        max_gap,
        "标题".into(),
        "引文".into(),
    )
}

#[tauri::command]
pub fn start_batch(
    app: AppHandle,
    excel_path: String,
    title_col: String,
    out_col: String,
    human: bool,
    min_gap: f64,
    max_gap: f64,
) -> Result<(), String> {
    let path = PathBuf::from(&excel_path);
    if !path.exists() {
        return Err(format!("文件不存在：{excel_path}"));
    }
    run_task(
        app,
        vec![],
        Some(path),
        "batch".into(),
        human,
        min_gap,
        max_gap,
        title_col,
        out_col,
    )
}

#[allow(clippy::too_many_arguments)]
fn run_task(
    app: AppHandle,
    titles: Vec<String>,
    excel_path: Option<PathBuf>,
    mode: String,
    human: bool,
    min_gap: f64,
    max_gap: f64,
    title_col: String,
    out_col: String,
) -> Result<(), String> {
    // 并发守卫
    {
        let mut g = RUNNING.lock().unwrap();
        if *g {
            let _ = app.emit("log", "[系统] 已有任务在运行，请等待完成");
            return Ok(());
        }
        *g = true;
    }

    let _ = app.emit(
        "log",
        "[系统] 任务启动，正在打开浏览器（首次可能需手动通过验证码）...",
    );
    app.emit("run-state", true).ok();

    std::thread::spawn(move || {
        // 日志回调 → 通过 Tauri 事件实时推送到前端
        let log_app = app.clone();
        let log = move |msg: String| {
            let _ = log_app.emit("log", msg);
        };

        let opts = RunOpts {
            human,
            min_gap,
            max_gap,
            excel_path: excel_path.clone(),
            title_col: title_col.clone(),
            out_col: out_col.clone(),
            out_prefix: "citations".into(),
            log: Some(Box::new(log)),
        };

        let result = browser::run(&titles, &opts);
        match &result {
            Ok(records) => {
                let dtos: Vec<RecordDto> = records
                    .iter()
                    .map(|r| RecordDto {
                        title: r.title.clone(),
                        citation: r.citation.clone(),
                        success: r.success,
                        skipped: r.skipped,
                        error: r.error.clone(),
                    })
                    .collect();
                let _ = app.emit(
                    "task-done",
                    TaskResult {
                        mode: mode.clone(),
                        records: dtos,
                    },
                );
            }
            Err(e) => {
                let _ = app.emit("log", format!("[错误] {e}"));
            }
        }

        // 解除并发守卫
        let mut g = RUNNING.lock().unwrap();
        *g = false;
        let _ = app.emit("run-state", false);
    });

    Ok(())
}

// ════════════════════════════════════════════
//  更新检测
// ════════════════════════════════════════════
#[tauri::command]
pub fn check_update() -> UpdateInfoDto {
    let updater = Updater {
        owner: GITEE_OWNER.into(),
        repo: GITEE_REPO.into(),
        token: GITEE_TOKEN.into(),
        current: env!("CARGO_PKG_VERSION").into(),
    };
    match updater.check() {
        Ok(info) => UpdateInfoDto {
            has_update: info.has_update,
            latest: info.latest,
            url: info.url,
            notes: info.notes,
            download_url: info.download_url,
        },
        Err(_) => UpdateInfoDto::default(),
    }
}

// ════════════════════════════════════════════
//  自更新（下载新版本 → 写替换脚本 → 重启）
// ════════════════════════════════════════════
/// 触发自更新：在后台线程下载并替换自身，完成后主动退出以解锁 exe。
///
/// 真正的下载 / 替换逻辑在 `do_update` 中，本命令立即返回以免阻塞 UI 主线程。
#[tauri::command]
pub fn perform_update(app: AppHandle, download_url: String) -> Result<(), String> {
    if download_url.trim().is_empty() {
        return Err("缺少下载地址，无法更新".into());
    }
    std::thread::spawn(move || {
        if let Err(e) = do_update(&app, &download_url) {
            let _ = app.emit("log", format!("[更新] ⚠ 更新失败：{e}"));
        }
    });
    Ok(())
}

/// 实际执行：下载 → 写 bat → 以 DETACHED 方式启动 bat → 退出当前进程。
///
/// 进程退出后 exe 文件解锁，bat 才能 `move /Y` 覆盖成功。
fn do_update(app: &AppHandle, download_url: &str) -> Result<(), String> {
    let _ = app.emit("log", "[更新] 正在下载新版本（约 22MB）...");

    let tmp = std::env::temp_dir();
    let new_exe = tmp.join(format!("{APP_NAME}_new.exe"));
    // 清理上一次可能残留的临时文件，避免 move 到旧文件
    let _ = std::fs::remove_file(&new_exe);

    cnki_citation_rs::update::download(download_url, &new_exe)?;

    let _ = app.emit("log", "[更新] 下载完成，正在准备替换...");

    let current = std::env::current_exe().map_err(|e| e.to_string())?;
    let bat = tmp.join(format!("{APP_NAME}_update.bat"));
    std::fs::write(&bat, UPDATE_BAT).map_err(|e| format!("写入更新脚本失败：{e}"))?;

    // DETACHED_PROCESS(0x08) + CREATE_NEW_PROCESS_GROUP(0x200)：
    // bat 与当前进程解耦，当前进程退出后 bat 仍继续跑（负责替换 + 重启）。
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        Command::new(&bat)
            .arg(&new_exe)
            .arg(&current)
            .creation_flags(0x08 | 0x200)
            .spawn()
            .map_err(|e| format!("启动更新脚本失败：{e}"))?;
    }
    #[cfg(not(windows))]
    {
        // 非 Windows（开发/跨平台兜底）：直接覆盖后启动
        let _ = std::fs::rename(&new_exe, &current);
        Command::new(&current)
            .spawn()
            .map_err(|e| format!("启动新版失败：{e}"))?;
        let _ = std::fs::remove_file(&bat);
    }

    let _ = app.emit("log", "[更新] 更新脚本已启动，即将重启...");
    // 略等 bat 起来，再退出解锁 exe
    std::thread::sleep(std::time::Duration::from_millis(800));
    std::process::exit(0);
}

/// 更新 bat（纯 ASCII，路径通过 `%1`/`%2` 传入，规避 GBK 编码与中文路径问题）。
///
/// - `%1` = 下载到 temp 的新 exe；`%2` = 当前正在运行的 exe。
/// - 每 2 秒尝试 `move /Y`，直到源文件不存在（即移动成功）或重试 30 次（60s 超时）。
/// - 仅当移动成功才 `cd` 到安装目录并 `start` 新 exe，最后 `del` 自身。
const UPDATE_BAT: &str = "@echo off\r\n\
set \"SRC=%~1\"\r\n\
set \"DST=%~2\"\r\n\
set \"OK=0\"\r\n\
for /L %%i in (1,1,30) do (\r\n\
  move /Y \"%SRC%\" \"%DST%\" >nul 2>&1\r\n\
  if not exist \"%SRC%\" (\r\n\
    set \"OK=1\"\r\n\
    goto :done\r\n\
  )\r\n\
  timeout /t 2 >nul\r\n\
)\r\n\
:done\r\n\
if \"%OK%\"==\"1\" (\r\n\
  for %%I in (\"%DST%\") do set \"DSTDIR=%%~dpI\"\r\n\
  cd /d \"%DSTDIR%\"\r\n\
  start \"\" \"%DST%\"\r\n\
)\r\n\
del \"%~f0\"\r\n";

// ════════════════════════════════════════════
//  历史记录清理
// ════════════════════════════════════════════
fn is_history_file(path: &PathBuf) -> bool {
    if !path.is_file() {
        return false;
    }
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();
    matches!(ext.as_str(), "txt" | "json" | "png")
}

#[tauri::command]
pub fn history_count() -> u32 {
    if let Ok(paths) = config::resolve_paths() {
        if let Ok(entries) = std::fs::read_dir(&paths.output) {
            return entries
                .flatten()
                .filter(|e| is_history_file(&e.path()))
                .count() as u32;
        }
    }
    0
}

#[tauri::command]
pub fn clean_history() -> Result<u32, String> {
    let paths = config::resolve_paths().map_err(|e| e.to_string())?;
    let mut removed = 0u32;
    if let Ok(entries) = std::fs::read_dir(&paths.output) {
        for e in entries.flatten() {
            let p = e.path();
            if is_history_file(&p) {
                let _ = std::fs::remove_file(&p);
                removed += 1;
            }
        }
    }
    Ok(removed)
}

// ════════════════════════════════════════════
//  模板下载 / 外部打开
// ════════════════════════════════════════════
/// 把内置 Excel 模板写入目标路径（dest 由前端通过保存对话框选定）。
#[tauri::command]
pub fn download_template(dest: String) -> Result<String, String> {
    let data = include_bytes!("../../frontend/批量引文模板.xlsx");
    std::fs::write(&dest, data).map_err(|e| e.to_string())?;
    Ok(dest)
}

/// 建议的保存目录（下载文件夹，不存在时回退桌面 / 用户目录）。
///
/// 前端把它拼成**绝对路径**再传给 dialog 插件：插件对相对路径的处理有坑
/// （相对且不存在的路径会被当成「目录」而不是文件名）。
#[tauri::command]
pub fn default_save_dir() -> String {
    #[cfg(windows)]
    {
        let base = std::env::var("USERPROFILE").unwrap_or_default();
        if base.is_empty() {
            return String::new();
        }
        let downloads = format!("{base}\\Downloads");
        if std::path::Path::new(&downloads).is_dir() {
            return downloads;
        }
        let desktop = format!("{base}\\Desktop");
        if std::path::Path::new(&desktop).is_dir() {
            return desktop;
        }
        base
    }
    #[cfg(not(windows))]
    {
        std::env::var("HOME").unwrap_or_default()
    }
}

/// 在系统默认程序中打开文件 / 文件夹 / URL（Windows 用 `cmd /c start`）。
#[tauri::command]
pub fn open_path(path: String) -> Result<(), String> {
    open_in_explorer(&path)
}

/// 打开输出目录（引文产物所在位置）。
#[tauri::command]
pub fn open_output() -> Result<(), String> {
    let paths = config::resolve_paths().map_err(|e| e.to_string())?;
    let p = paths.output.to_string_lossy().to_string();
    open_in_explorer(&p)
}

/// 当前版本号（供前端展示）。
#[tauri::command]
pub fn get_version() -> String {
    env!("CARGO_PKG_VERSION").into()
}

// ════════════════════════════════════════════
//  系统主题跟随
// ════════════════════════════════════════════
/// 读取 Windows 注册表的「应用使用亮色主题」开关。
///
/// 直连 advapi32 的 Reg* API（零额外依赖）。相比 WebView 的
/// `prefers-color-scheme`，它能在程序运行期间被反复轮询，
/// 从而实时跟随用户在系统设置里的切换。
#[cfg(windows)]
mod winreg_theme {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use std::ptr;

    type Hkey = *mut std::ffi::c_void;

    const HKEY_CURRENT_USER: Hkey = 0x8000_0001usize as Hkey;
    const KEY_READ: u32 = 0x0002_0019;
    const REG_DWORD: u32 = 4;

    #[link(name = "advapi32")]
    extern "system" {
        fn RegOpenKeyExW(
            key: Hkey,
            sub_key: *const u16,
            options: u32,
            sam_desired: u32,
            result: *mut Hkey,
        ) -> i32;
        fn RegQueryValueExW(
            key: Hkey,
            value_name: *const u16,
            reserved: *mut u32,
            ty: *mut u32,
            data: *mut u8,
            data_size: *mut u32,
        ) -> i32;
        fn RegCloseKey(key: Hkey) -> i32;
    }

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(Some(0)).collect()
    }

    /// `Some(true)` 系统为亮色 / `Some(false)` 暗色 / `None` 读取失败。
    pub fn apps_use_light_theme() -> Option<bool> {
        unsafe {
            let sub = wide(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            let name = wide("AppsUseLightTheme");
            let mut hkey: Hkey = ptr::null_mut();

            if RegOpenKeyExW(HKEY_CURRENT_USER, sub.as_ptr(), 0, KEY_READ, &mut hkey) != 0 {
                return None;
            }

            let mut ty: u32 = 0;
            let mut val: u32 = 1;
            let mut size: u32 = std::mem::size_of::<u32>() as u32;
            let status = RegQueryValueExW(
                hkey,
                name.as_ptr(),
                ptr::null_mut(),
                &mut ty,
                &mut val as *mut u32 as *mut u8,
                &mut size,
            );
            RegCloseKey(hkey);

            if status != 0 || ty != REG_DWORD {
                None
            } else {
                Some(val != 0)
            }
        }
    }
}

/// 上一次已应用到原生窗口的主题，避免每 2 秒无意义地重复设置。
static LAST_THEME: Mutex<String> = Mutex::new(String::new());

/// 返回 `"dark"` / `"light"`；读取失败时返回空串，
/// 前端据此跳过设置，让 CSS 的 `prefers-color-scheme` 兜底。
///
/// 主题发生变化时，同步应用到原生窗口 —— 这样 WebView 的
/// `prefers-color-scheme`、滚动条等原生元素也会跟着切换。
#[tauri::command]
pub fn system_theme(app: AppHandle) -> String {
    #[cfg(windows)]
    let theme: String = match winreg_theme::apps_use_light_theme() {
        Some(light) => {
            if light {
                "light".into()
            } else {
                "dark".into()
            }
        }
        None => String::new(),
    };
    #[cfg(not(windows))]
    let theme: String = String::new();

    if !theme.is_empty() {
        let mut last = LAST_THEME.lock().unwrap();
        if *last != theme {
            *last = theme.clone();
            if let Some(w) = app.get_webview_window("main") {
                let t = if theme == "dark" {
                    Some(Theme::Dark)
                } else {
                    Some(Theme::Light)
                };
                let _ = w.set_theme(t);
            }
        }
    }

    theme
}

#[cfg(windows)]
fn open_in_explorer(path: &str) -> Result<(), String> {
    std::process::Command::new("cmd")
        .args(["/c", "start", "", path])
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[cfg(not(windows))]
fn open_in_explorer(path: &str) -> Result<(), String> {
    // 非 Windows（开发/跨平台兜底）：尝试 xdg-open / open
    let cmd = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
    std::process::Command::new(cmd)
        .arg(path)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}
