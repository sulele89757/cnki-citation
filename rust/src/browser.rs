//! Chrome 驱动引擎（对标 Python 的 Playwright 流程）
//!
//! 使用 headless_chrome 直接拉起**系统 Chrome** + 持久化 Profile + 去自动化标志 + stealth，
//! 流程：首页 -> 直接构造搜索 URL -> JS 定位论文并点击「引用」-> 正则提取 GB/T 7714-2025。

use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::Duration;

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

/// 探测系统已安装的 Chrome / Edge（对标 `channel="chrome"` 回退到内置 Chromium）。
fn find_chrome() -> Option<PathBuf> {
    let candidates = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ];
    candidates.iter().map(PathBuf::from).find(|p| p.exists())
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
fn click_cite(tab: &Tab, title: &str) -> bool {
    let tt = serde_json::to_string(title).unwrap_or_default();
    let js = format!(
        r#"
        (function() {{
            var rows = document.querySelectorAll('#gridTable tr, table.result-grid-list tr');
            var tt = {tt};
            for (var i = 0; i < rows.length; i++) {{
                var row = rows[i];
                var nameLink = row.querySelector('.name a, td.name a, a.fz14');
                if (!nameLink || nameLink.textContent.indexOf(tt) < 0) continue;
                var as = row.querySelectorAll('a');
                for (var j = 0; j < as.length; j++) {{
                    var a = as[j];
                    var h = (a.href || '').toLowerCase();
                    var t = (a.title || '') + (a.textContent || '');
                    var img = a.querySelector('img');
                    var src = img ? (img.src || '').toLowerCase() : '';
                    if (h.indexOf('cite') >= 0 || t.indexOf('引用') >= 0 ||
                        src.indexOf('cite') >= 0 || src.indexOf('quote') >= 0) {{
                        a.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }})()
    "#
    );
    eval_bool(tab, &js)
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
    log(opts, "1/4 启动浏览器（系统 Chrome + 持久化 Profile）");
    let mut builder = LaunchOptionsBuilder::default();
    builder
        .headless(false)
        .user_data_dir(Some(paths.profile.clone()))
        .args(vec![
            OsStr::new("--disable-blink-features=AutomationControlled"),
            OsStr::new("--disable-infobars"),
            OsStr::new("--no-sandbox"),
            OsStr::new("--window-size=1920,1080"),
        ])
        .ignore_default_args(vec![OsStr::new("--enable-automation")])
        .window_size(Some((1920, 1080)))
        .idle_browser_timeout(Duration::from_secs(60));
    if let Some(p) = find_chrome() {
        builder.path(Some(p));
        log(opts, "   已使用系统 Chrome");
    } else {
        log(opts, "   未检测到系统 Chrome，回退到 headless_chrome 自带 Chromium");
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
        sleep(Duration::from_secs(3));

        // 检测是否打开了新标签页（CNKI 引用有时 window.open）
        let tabs_guard = browser.get_tabs().lock().unwrap();
        let cite_tab: &Tab = if tabs_guard.len() > 1 {
            tabs_guard.last().unwrap().as_ref()
        } else {
            tab
        };
        let _ = cite_tab.wait_until_navigated();
        sleep(Duration::from_secs(1));

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
