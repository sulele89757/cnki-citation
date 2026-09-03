//! 路径与配置（对标 Python 顶部 BASE_DIR / OUTPUT_DIR / PROFILE_DIR 逻辑）
//!
//! 开发态（exe 与 `Cargo.toml` 同目录）：Profile/输出落在项目里，便于调试。
//! 发布态（exe 被复制到别处）：落在 `~/ .cnki_citation`，保证 Cookie/登录态跨运行持久。

use std::path::PathBuf;

pub struct Paths {
    pub base: PathBuf,
    pub output: PathBuf,
    pub profile: PathBuf,
}

/// 解析基线目录与子目录，必要时创建。
pub fn resolve_paths() -> anyhow::Result<Paths> {
    let exe = std::env::current_exe()?;
    let exe_dir = exe
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));

    // 开发态判定：exe 同目录存在 Cargo.toml
    let base = if exe_dir.join("Cargo.toml").exists() {
        exe_dir
    } else {
        let home = std::env::var("USERPROFILE")
            .or_else(|_| std::env::var("HOME"))
            .unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".cnki_citation")
    };

    let output = base.join("output");
    let profile = base.join(".chrome_profile");
    std::fs::create_dir_all(&output)?;
    std::fs::create_dir_all(&profile)?;

    Ok(Paths {
        base,
        output,
        profile,
    })
}

/// CNKI 相关常量
pub const CNKI_HOME: &str = "https://www.cnki.net";
pub const SEARCH_URL_TEMPLATE: &str =
    "https://kns.cnki.net/kns8s/defaultresult/index?kw={kw}&korder=TI";
