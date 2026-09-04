// offline_join.rs — Gitee 分卷离线包的"自合并引导器"
//
// 用法场景：CNKI 引文工具 离线安装包（内置 WebView2，~150MB）超过 Gitee
// 附件 100MB 上限，发布时被切成：
//   本程序（CNKICitationTool-rs-offline.exe）
//   + CNKICitationTool-rs-offline.p2 / .p3 / ...（每份 ≤95MB 的数据分卷）
// 用户把分卷与引导器放同一目录，双击引导器 → 自动按序拼接回
//   CNKICitationTool-rs-offline-installer.exe → 直接启动安装。
// 无需 7-Zip、无需 cmd、无任何第三方依赖。
//
// 调试开关：设置环境变量 CNKI_JOIN_NO_RUN=1 时只合并不启动（供自动化/CI 校验）。

use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

#[cfg(windows)]
#[link(name = "kernel32")]
extern "system" {
    fn SetConsoleOutputCP(cp: u32) -> i32;
}

fn main() {
    #[cfg(windows)]
    unsafe {
        // 控制台输出切 UTF-8，避免中文乱码
        SetConsoleOutputCP(65001);
    }

    let exe = match env::current_exe() {
        Ok(p) => p,
        Err(e) => {
            println!("无法定位自身路径: {e}");
            keep_window();
            std::process::exit(1);
        }
    };
    let dir = match exe.parent() {
        Some(d) => d.to_path_buf(),
        None => {
            println!("无法确定所在目录");
            keep_window();
            std::process::exit(1);
        }
    };

    let stem = exe
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "CNKICitationTool-rs-offline".to_string());

    // 收集同目录下连续存在的分卷：<stem>.p2, <stem>.p3, ...
    let mut parts: Vec<PathBuf> = Vec::new();
    let mut idx = 2u32;
    loop {
        let p = dir.join(format!("{stem}.p{idx}"));
        if p.is_file() {
            parts.push(p);
            idx += 1;
        } else {
            break;
        }
    }

    if parts.is_empty() {
        println!("错误：没有找到数据分卷。");
        println!("请把以下文件与本程序放在同一文件夹后再运行：");
        println!("  {stem}.p2, {stem}.p3, ...");
        keep_window();
        std::process::exit(1);
    }

    let total: u64 = parts.iter().map(|p| fs::metadata(p).map(|m| m.len()).unwrap_or(0)).sum();
    let out = dir.join(format!("{stem}-installer.exe"));

    println!("========================================");
    println!("  CNKI 引文工具 离线安装包 分卷合并");
    println!("========================================");
    println!("数据分卷 {} 个，共 {:.1} MB", parts.len(), total as f64 / 1048576.0);
    println!("正在拼接...");

    match merge(&parts, &out) {
        Ok(()) => println!("完成：{}", out.display()),
        Err(e) => {
            println!("合并失败：{e}");
            let _ = fs::remove_file(&out);
            keep_window();
            std::process::exit(1);
        }
    }

    // 调试/CI 校验：只合并不启动
    if env::var_os("CNKI_JOIN_NO_RUN").is_some() {
        return;
    }

    if let Err(e) = Command::new(&out).spawn() {
        println!("启动安装程序失败：{e}，请手动双击 {out:?}");
        keep_window();
    }
}

fn merge(parts: &[PathBuf], out: &Path) -> io::Result<()> {
    let mut dst = fs::File::create(out)?;
    // 注意：Windows 上 MSVC 链接默认主线程栈仅 1MB，大数组必须放堆上
    let mut buf = vec![0u8; 256 * 1024];
    for p in parts {
        let mut src = fs::File::open(p)?;
        loop {
            let n = src.read(&mut buf)?;
            if n == 0 {
                break;
            }
            dst.write_all(&buf[..n])?;
        }
    }
    dst.flush()
}

fn keep_window() {
    let mut s = String::new();
    let _ = io::stdin().read_line(&mut s);
}
