//! Chrome 驱动引擎（对标 Python 的 Playwright 流程）
//!
//! 使用 headless_chrome 直接拉起**系统 Chrome/Edge** + 持久化 Profile + 去自动化标志 + stealth，
//! 流程：首页 -> 直接构造搜索 URL -> JS 定位论文并点击「引用」-> 正则提取 GB/T 7714-2025。
//! 若本机既无 Chrome 也无 Edge：自动从 npmmirror（Chrome for Testing 国内镜像）下载
//! 一份 Chromium 到 `<base>/chromium` 兜底驱动（仅首次，约 200MB）。

use std::ffi::OsStr;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread::sleep;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// 创建子进程命令。
///
/// Windows 下附加 `CREATE_NO_WINDOW (0x08000000)`：父进程是 GUI 子系统（Tauri），
/// 若不加此标志，每次 spawn 控制台子程序（如 `reg`/`tar`）都会让 Windows 分配一个
/// 一闪而过的 cmd 控制台窗口——点击「开始」时 `find_chrome` 连查 6 次注册表就会造成
/// 「疯狂弹一堆 cmd 窗口」的现象。加该标志后子进程在后台静默运行，不再弹窗。
#[cfg(windows)]
fn quiet_cmd(program: &str) -> Command {
    let mut c = Command::new(program);
    c.creation_flags(0x08000000);
    c
}

#[cfg(not(windows))]
fn quiet_cmd(program: &str) -> Command {
    Command::new(program)
}

use headless_chrome::browser::tab::Tab;
use headless_chrome::protocol::cdp::Page;
use headless_chrome::{Browser, LaunchOptionsBuilder};
use serde::Serialize;
use serde_json::Value;

use crate::behavior;
use crate::config::{self, Paths};
use crate::excel;

/// 运行选项（对标 Python `run()` 的参数）。
pub struct RunOpts {
    pub human: bool,
    pub min_gap: f64,
    pub max_gap: f64,
    pub excel_path: Option<PathBuf>,
    pub title_col: String,
    pub out_col: String,
    pub out_prefix: String,
    /// 日志回调（GUI 实时刷新；为 None 时打印到 stdout）。
    pub log: Option<Box<dyn Fn(String) + Send + Sync>>,
}

impl Default for RunOpts {
    fn default() -> Self {
        RunOpts {
            human: true,
            min_gap: 5.0,
            max_gap: 12.0,
            excel_path: None,
            title_col: "标题".into(),
            out_col: "引文".into(),
            out_prefix: "citations".into(),
            log: None,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Record {
    pub title: String,
    pub citation: Option<String>,
    pub success: bool,
    pub skipped: bool,
    pub error: Option<String>,
}

fn log(opts: &RunOpts, msg: &str) {
    match &opts.log {
        Some(f) => f(msg.to_string()),
        None => println!("{msg}"),
    }
}

/// 兜底 Chromium 版本（Chrome for Testing；升级时与镜像目录保持同步）。
const FALLBACK_CHROMIUM_VERSION: &str = "151.0.7922.34";
const FALLBACK_CHROMIUM_URL: &str = "https://npmmirror.com/mirrors/chrome-for-testing/";

/// 探测系统已安装的 Chrome / Edge。
///
/// 优先级：注册表 App Paths（HKLM/HKCU，含 per-user 安装与 WOW6432Node）
/// → 用户目录常见位置 → 固定 Program Files 路径。
fn find_chrome() -> Option<PathBuf> {
    let mut cands: Vec<PathBuf> = Vec::new();

    // ① 注册表 App Paths：reg query 读默认值即可拿到完整 exe 路径
    let reg_keys = [
        ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
    ];
    for (root, key) in reg_keys {
        let path = format!(r"{root}\{key}");
        let out = quiet_cmd("reg")
            .arg("query")
            .arg(&path)
            .arg("/ve")
            .output();
        if let Ok(out) = out {
            if out.status.success() {
                let text = String::from_utf8_lossy(&out.stdout);
                if let Some(p) = parse_reg_default(&text) {
                    cands.push(PathBuf::from(p));
                }
            }
        }
    }

    // ② per-user 安装（无管理员权限装到 %LOCALAPPDATA%）
    if let Ok(home) = std::env::var("USERPROFILE") {
        cands.push(PathBuf::from(format!(
            r"{home}\AppData\Local\Google\Chrome\Application\chrome.exe"
        )));
        cands.push(PathBuf::from(format!(
            r"{home}\AppData\Local\Microsoft\Edge\Application\msedge.exe"
        )));
    }

    // ③ 经典 Program Files 路径
    for p in [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ] {
        cands.push(PathBuf::from(p));
    }

    cands.into_iter().find(|p| p.exists())
}

/// 从 `reg query ... /ve` 输出中解析默认值路径（兼容中英文 locale）。
fn parse_reg_default(text: &str) -> Option<String> {
    for line in text.lines() {
        if !line.contains("REG_SZ") {
            continue;
        }
        // "默认值类型 REG_SZ    路径(可能含空格)" —— 取 REG_SZ 之后的部分 trim 即可
        let rest = line.split("REG_SZ").nth(1)?.trim();
        if !rest.is_empty() && Path::new(rest).extension().is_some() {
            return Some(rest.to_string());
        }
    }
    None
}

/// 兜底 Chromium 的 exe 路径（<base>/chromium/chrome-win64/chrome.exe）。
fn fallback_chromium_exe(paths: &Paths) -> PathBuf {
    paths
        .base
        .join("chromium")
        .join("chrome-win64")
        .join("chrome.exe")
}

/// 确保兜底 Chromium 就绪：已下载直接返回；否则下载+解压（npmmirror，约 200MB）。
/// 返回 None 表示失败（调用方给用户友好报错）。
fn ensure_fallback_chromium(
    paths: &Paths,
    on_log: &dyn Fn(&str),
) -> anyhow::Result<Option<PathBuf>> {
    let exe = fallback_chromium_exe(paths);
    if exe.exists() {
        return Ok(Some(exe));
    }

    let dir = paths.base.join("chromium");
    std::fs::create_dir_all(&dir)?;
    let url = format!(
        "{FALLBACK_CHROMIUM_URL}{FALLBACK_CHROMIUM_VERSION}/win64/chrome-win64.zip"
    );
    let zip = dir.join(format!("chrome-{FALLBACK_CHROMIUM_VERSION}.zip"));

    on_log("本机未检测到 Chrome / Edge，将下载 Chromium 内核保证程序可用（约 200MB，npmmirror 国内镜像，仅首次）");
    if let Err(e) = http_download(&url, &zip, on_log) {
        let _ = std::fs::remove_file(&zip);
        anyhow::bail!("Chromium 下载失败：{e}");
    }
    on_log("下载完成，正在解压（约需 1-2 分钟）...");

    // 用 Windows 自带 bsdtar（Win10 1803+ 均有）解压，产出 chrome-win64/
    let status = quiet_cmd("tar")
        .arg("-xf")
        .arg(&zip)
        .arg("-C")
        .arg(&dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    let _ = std::fs::remove_file(&zip);

    match status {
        Ok(s) if s.success() && exe.exists() => {
            on_log(&format!("Chromium 就绪：{}", exe.display()));
            Ok(Some(exe))
        }
        _ => Ok(None),
    }
}

/// 流式 HTTP 下载（ureq），每 ~10% 回调一条进度日志。
fn http_download(url: &str, dest: &Path, on_log: &dyn Fn(&str)) -> anyhow::Result<()> {
    let resp = ureq::get(url).call()?;
    let total: u64 = resp
        .header("Content-Length")
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    let mut reader = resp.into_reader();
    let mut out = std::fs::File::create(dest)?;
    let mut buf = [0u8; 1 << 20]; // 1MB 块
    let mut got: u64 = 0;
    let mut last_tick: Option<u64> = None;
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        got += n as u64;
        if total > 0 {
            let tick = got * 10 / total;
            if last_tick != Some(tick) {
                last_tick = Some(tick);
                on_log(&format!(
                    "下载 {}MB/{}MB（{}%）",
                    got / 1048576,
                    total / 1048576,
                    got * 100 / total
                ));
            }
        }
    }
    if total > 0 && got < total {
        anyhow::bail!("下载不完整：{got}/{total} 字节");
    }
    Ok(())
}

/// 最小 URL 编码（unreserved 字符原样，其余按 UTF-8 字节 %XX）。
fn urlencode(s: &str) -> String {
    let mut out = String::new();
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' =>
                out.push(b as char),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

fn eval_value(tab: &Tab, js: &str) -> Option<Value> {
    match tab.evaluate(js, false) {
        Ok(ro) => ro.value,
        Err(e) => {
            eprintln!("[eval] {e}");
            None
        }
    }
}

fn eval_string(tab: &Tab, js: &str) -> Option<String> {
    eval_value(tab, js).and_then(|v| v.as_str().map(|s| s.to_string()))
}

#[allow(dead_code)]
fn eval_bool(tab: &Tab, js: &str) -> bool {
    eval_value(tab, js).and_then(|v| v.as_bool()).unwrap_or(false)
}

/// 检测是否被拦截 / 需验证码 / 需登录。需人工时在终端等待回车。
fn check_block(tab: &Tab, opts: &RunOpts) {
    sleep(Duration::from_secs(1));
    let url = tab.get_url().to_lowercase();
    let title = eval_string(tab, "document.title || ''").unwrap_or_default();
    let need = url.contains("verify")
        || url.contains("captcha")
        || url.contains("valid")
        || url.contains("login")
        || url.contains("passport")
        || title.contains("验证")
        || title.contains("403")
        || title.contains("拒绝")
        || title.contains("登录");
    if need {
        log(opts, "⚠ 需人工介入：请在浏览器窗口中完成登录 / 验证码，完成后回车继续...");
        let mut s = String::new();
        let _ = std::io::stdin().read_line(&mut s);
        sleep(Duration::from_secs(1));
    }
}

fn search_paper(tab: &Tab, title: &str, opts: &RunOpts, paths: &Paths) {
    log(opts, &format!("2/4 搜索：{title}"));
    check_block(tab, opts);

    let kw = urlencode(title);
    let url = format!("https://kns.cnki.net/kns8s/defaultresult/index?kw={kw}&korder=TI");
    let _ = tab.navigate_to(&url);
    let _ = tab.wait_until_navigated();
    sleep(if opts.human {
        Duration::from_secs(2)
    } else {
        Duration::from_secs(3)
    });
    let _ = tab.wait_until_navigated();
    sleep(Duration::from_secs(2));

    log(opts, &format!("   当前 URL: {}", tab.get_url()));
    if let Ok(d) = tab.capture_screenshot(Page::CaptureScreenshotFormatOption::Png, None, None, true)
    {
        let _ = std::fs::write(paths.output.join("debug_search_result.png"), d);
    }
}

/// 在当前页内 JS 定位论文行并点击「引用」按钮，返回是否点击成功。
///
/// CNKI 搜索结果行的「引用」图标通常是 `<li>` / `<span>` 套 `<img src="...quote.png">`，
/// **不是 `<a>`**。原实现按 `<a>` + href/文字匹配极易错中「导出」「详情」等链接。
/// 改为：精确命中 `img[src*='quote']` 或 `[title='引用']` 等，再 click 其可点击祖先。
fn click_cite(tab: &Tab, title: &str) -> bool {
    let tt = serde_json::to_string(title).unwrap_or_default();
    let js = format!(
        r#"
        (function() {{
            var rows = document.querySelectorAll('#gridTable tr, table.result-grid-list tr');
            var tt = {tt};
            for (var i = 0; i < rows.length; i++) {{
                var row = rows[i];
                if (row.textContent.indexOf(tt) < 0) continue;
                // 1) 直接匹配引用图标
                var img = row.querySelector("img[src*='quote'], img[src*='cite'], img[alt='引用'], img[title='引用']");
                var target = img;
                if (!target) {{
                    // 2) 备选：title / data-action 属性
                    target = row.querySelector("[title='引用'], [data-action='cite'], [onclick*='cite']");
                }}
                if (!target) return false;
                // click 可点击祖先（a / li / span / button / i），确保触发 layer.open
                var node = target;
                for (var k = 0; k < 4 && node && node !== row; k++) {{
                    var tag = (node.tagName || '').toLowerCase();
                    if (tag === 'a' || tag === 'li' || tag === 'span' || tag === 'button' || tag === 'i' || node.onclick) {{
                        node.click();
                        return true;
                    }}
                    node = node.parentNode;
                }}
                target.click();
                return true;
            }}
            return false;
        }})()
    "#
    );
    eval_bool(tab, &js)
}

/// 等待 CNKI 引用弹窗 / iframe / textarea 出现（最长 `max_wait`）。
/// CNKI 引用通常是 layer.open 弹出的 div，里面再嵌套 iframe；
/// 若直接 window.open 新 tab，textarea 直接出现在新页面。
/// 任一信号出现即返回，避免固定 sleep 在慢机器/最小化时误判空引文。
fn wait_for_citation(tab: &Tab, max_wait: Duration) {
    let js = r#"
        (function() {
            if (document.querySelector('textarea')) return true;
            if (document.querySelector("iframe[src*='cite'], iframe[name*='cite'], iframe[id*='cite']")) return true;
            // layui layer 弹层
            if (document.querySelector('.layui-layer, .layui-layer-iframe, [class*="layer"]')) return true;
            // 任意可见的 modal / 引用样式
            if (document.querySelector("[class*='cite'], [id*='cite'], [class*='Modal'], [class*='modal']")) return true;
            return false;
        })()
    "#;
    let deadline = std::time::Instant::now() + max_wait;
    while std::time::Instant::now() < deadline {
        if eval_bool(tab, js) {
            return;
        }
        sleep(Duration::from_millis(300));
    }
}

/// 从引用页提取 GB/T 7714-2025 引文（textarea 优先，否则正文）。
fn extract_from_tab(tab: &Tab) -> Option<String> {
    if let Some(v) = eval_string(tab, "(()=>{var t=document.querySelector('textarea');return t?t.value:'';})()")
    {
        if v.contains("7714") || (v.contains("[J]") && v.len() > 40) {
            if let Some(c) = crate::citation::extract_citation(&v) {
                return Some(c);
            }
        }
    }
    if let Some(body) = eval_string(tab, "(()=>document.body?document.body.innerText:'')()") {
        if let Some(c) = crate::citation::extract_citation(&body) {
            return Some(c);
        }
    }
    None
}

fn launch_browser(opts: &RunOpts, paths: &Paths) -> anyhow::Result<Browser> {
    log(opts, "1/4 启动浏览器（Chrome/Edge → 无则自动下载 Chromium）");
    let mut builder = LaunchOptionsBuilder::default();
    builder
        .headless(false)
        .user_data_dir(Some(paths.profile.clone()))
        .args(vec![
            OsStr::new("--disable-blink-features=AutomationControlled"),
            OsStr::new("--disable-infobars"),
            OsStr::new("--no-sandbox"),
            OsStr::new("--window-size=1920,1080"),
            // 禁止后台节流：窗口被最小化 / 被其它窗口遮挡时，Chrome 会判定页面 hidden 并挂起
            // 定时器与渲染进程，导致 CNKI 页面卡住、抓取失败。加以下标志让其在后台仍照常运行，
            // 用户可放心最小化或切到别的窗口去做别的事。
            OsStr::new("--disable-background-timer-throttling"),
            OsStr::new("--disable-backgrounding-occluded-windows"),
            OsStr::new("--disable-renderer-backgrounding"),
            OsStr::new("--disable-features=CalculateNativeWinOcclusion"),
        ])
        .ignore_default_args(vec![OsStr::new("--enable-automation")])
        .window_size(Some((1920, 1080)))
        .idle_browser_timeout(Duration::from_secs(60));

    // ① 系统 Chrome / Edge（注册表 + 常见路径探测）
    if let Some(p) = find_chrome() {
        builder.path(Some(p.clone()));
        log(
            opts,
            &format!("   已使用系统 {}", p.file_name().unwrap_or_default().to_string_lossy()),
        );
    } else {
        // ② 自动下载 Chromium 兜底（约 200MB，仅首次；日志实时透传）
        log(opts, "   未检测到系统 Chrome / Edge");
        let on_log = |m: &str| log(opts, m);
        match ensure_fallback_chromium(paths, &on_log) {
            Ok(Some(p)) => {
                builder.path(Some(p));
                log(opts, "   已使用自动下载的 Chromium（首次已联网下载）");
            }
            Ok(None) => anyhow::bail!(
                "Chromium 自动下载/解压后不可用。\n请安装 Google Chrome 或 Microsoft Edge 后重试。"
            ),
            Err(e) => anyhow::bail!("Chromium 兜底失败：{e:#}"),
        }
    }
    let options = builder.build()?;
    let browser = Browser::new(options)?;
    Ok(browser)
}

fn process_one(browser: &Browser, tab: &Tab, title: &str, opts: &RunOpts, paths: &Paths) -> Record {
    let mut rec = Record {
        title: title.to_string(),
        citation: None,
        success: false,
        skipped: false,
        error: None,
    };

    let outcome: anyhow::Result<Option<String>> = (|| -> anyhow::Result<Option<String>> {
        search_paper(tab, title, opts, paths);
        if !click_cite(tab, title) {
            if let Ok(d) =
                tab.capture_screenshot(Page::CaptureScreenshotFormatOption::Png, None, None, true)
            {
                let _ = std::fs::write(paths.output.join("search_results.png"), d);
            }
            anyhow::bail!("未找到论文「{title}」的引用按钮");
        }

        // 等待引用弹窗 / iframe 出现（最多 ~8s）。CNKI「引用」是 layer.open 弹层，
        // 动画 + iframe 加载加起来常超过 3s，固定 sleep 容易误判空引文。
        wait_for_citation(tab, Duration::from_secs(8));

        // 检测是否打开了新标签页（CNKI 引用有时 window.open）
        let tabs_guard = browser.get_tabs().lock().unwrap();
        let cite_tab: &Tab = if tabs_guard.len() > 1 {
            tabs_guard.last().unwrap().as_ref()
        } else {
            tab
        };
        let _ = cite_tab.wait_until_navigated();
        sleep(Duration::from_millis(500));

        match extract_from_tab(cite_tab) {
            Some(c) if c.len() > 20 => Ok(Some(c)),
            _ => anyhow::bail!("未能提取到有效引文内容"),
        }
    })();

    match outcome {
        Ok(Some(c)) => {
            rec.citation = Some(c.clone());
            rec.success = true;
            log(opts, &format!("✓ 成功 {c}"));
        }
        Ok(None) => {
            rec.error = Some("空引文".into());
        }
        Err(e) => {
            rec.error = Some(e.to_string());
            log(opts, &format!("✗ 失败 {e}"));
            if let Ok(d) =
                tab.capture_screenshot(Page::CaptureScreenshotFormatOption::Png, None, None, true)
            {
                let _ = std::fs::write(paths.output.join("error.png"), d);
            }
        }
    }
    rec
}

/// 主流程（对标 Python `run()`）。
pub fn run(titles: &[String], opts: &RunOpts) -> anyhow::Result<Vec<Record>> {
    let paths = config::resolve_paths()?;

    // Excel 模式：加载任务
    let mut excel = if let Some(p) = &opts.excel_path {
        Some(excel::load_excel(p, &opts.title_col, &opts.out_col)?)
    } else {
        None
    };
    let effective: Vec<String> = if let Some(ex) = &excel {
        ex.tasks.iter().map(|(_, t)| t.clone()).collect()
    } else {
        titles.to_vec()
    };
    if effective.is_empty() {
        log(opts, "没有需要处理的标题");
        return Ok(vec![]);
    }

    let browser = launch_browser(opts, &paths)?;
    let tab = browser.new_tab()?;
    crate::stealth::apply_stealth(&tab);
    let _ = tab.navigate_to(config::CNKI_HOME);
    let _ = tab.wait_until_navigated();
    sleep(Duration::from_secs(2));
    check_block(&tab, opts);

    let mut results: Vec<Record> = Vec::with_capacity(effective.len());
    for (i, title) in effective.iter().enumerate() {
        log(
            opts,
            &format!("进度 第 {}/{} 篇：{}", i + 1, effective.len(), title),
        );
        let row = excel.as_ref().map(|e| e.tasks[i].0);

        // 断点续传：已存在引文则跳过
        if let (Some(ex), Some(r)) = (excel.as_mut(), row) {
        let existing = ex
            .book
            .get_sheet(&0)
            .ok()
            .and_then(|ws| ws.get_cell((ex.out_idx, r)))
            .map(|c| c.get_value().trim().to_string());
            if let Some(v) = existing {
                if !v.is_empty() {
                    log(opts, "   该行列已存在引文，跳过（断点续传）");
                    results.push(Record {
                        title: title.clone(),
                        citation: Some(v),
                        success: true,
                        skipped: true,
                        error: None,
                    });
                    continue;
                }
            }
        }

        let rec = process_one(&browser, &tab, title, opts, &paths);
        let ok = rec.success && rec.citation.is_some();

        // 回填 Excel（成功后实时保存）
        if let (Some(ex), Some(r), true) = (excel.as_mut(), row, ok) {
            if let Some(cit) = &rec.citation {
                excel::backfill(ex, r, cit)?;
                log(opts, &format!("   已回填 Excel 第 {r} 行并保存"));
            }
        }
        results.push(rec);

        if i + 1 < effective.len() {
        let gap: f64 = if opts.human {
            behavior::gap_with_possible_long_pause(opts.min_gap, opts.max_gap)
        } else {
            behavior::random_gap(opts.min_gap, opts.max_gap)
        };
            log(opts, &format!("   间隔 {:.1}s 后继续...", gap));
            sleep(Duration::from_secs_f64(gap));
        }
    }

    // 写 txt / json 备份
    let real_ok = results.iter().filter(|r| r.success && !r.skipped).count();
    let skipped = results.iter().filter(|r| r.skipped).count();
    let failed = results.iter().filter(|r| !r.success).count();

    let mut lines = vec![format!(
        "# CNKI 引文导出（GB/T 7714-2025）\n# 导出时间：{}\n",
        chrono::Local::now().format("%Y-%m-%d %H:%M:%S")
    )];
    for (i, r) in results.iter().filter(|r| r.success).enumerate() {
        if let Some(c) = &r.citation {
            lines.push(format!("[{i}] {c}\n"));
        }
    }
    if failed > 0 {
        lines.push("\n# 以下篇目提取失败：\n".into());
        for r in &results {
            if !r.success {
                lines.push(format!("- {} -> {}\n", r.title, r.error.clone().unwrap_or_default()));
            }
        }
    }
    let _ = std::fs::write(
        paths.output.join(format!("{}.txt", opts.out_prefix)),
        lines.concat(),
    );
    let _ = std::fs::write(
        paths.output.join(format!("{}.json", opts.out_prefix)),
        serde_json::to_string_pretty(&results)?,
    );

    log(
        opts,
        &format!("完成：本次成功 {real_ok} 条，跳过(已存在) {skipped} 条，失败 {failed} 条"),
    );
    if let Some(p) = &opts.excel_path {
        log(opts, &format!("Excel：{}（已实时回填）", p.display()));
    }
    Ok(results)
}

#[allow(dead_code)]
fn _unused(_: &Path) {}
