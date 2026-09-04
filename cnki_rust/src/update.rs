//! Gitee Releases 更新检测（对标 Python `check_update`）

use crate::version;
use serde::Deserialize;
use std::io::Read;
use std::path::Path;
use std::time::Duration;

#[derive(Debug, Clone, Default)]
pub struct UpdateInfo {
    pub has_update: bool,
    pub latest: String,
    pub url: String,
    pub notes: String,
    pub download_url: String,
}

#[derive(Deserialize)]
struct Release {
    tag_name: Option<String>,
    name: Option<String>,
    html_url: Option<String>,
    body: Option<String>,
    id: Option<u64>,
}

#[derive(Deserialize)]
struct Attachment {
    name: Option<String>,
    id: Option<u64>,
}

/// 更新检测器，对标 Python 的 Gitee 配置。
pub struct Updater {
    pub owner: String,
    pub repo: String,
    /// 只读令牌（会被打包进 exe，务必仅授予本仓库只读权限）
    pub token: String,
    pub current: String,
}

impl Updater {
    pub fn check(&self) -> Result<UpdateInfo, String> {
        if self.owner.is_empty() {
            return Ok(UpdateInfo::default());
        }
        let api = format!(
            "https://gitee.com/api/v5/repos/{}/{}/releases/latest",
            self.owner, self.repo
        );

        let mut req = ureq::get(&api).timeout(Duration::from_secs(8));
        if !self.token.is_empty() {
            req = req.query("access_token", &self.token);
        }
        let resp = req.call().map_err(|e| format!("{e}"))?;
        let release: Release = resp.into_json().map_err(|e| format!("{e}"))?;

        let latest = release.tag_name.or(release.name).unwrap_or_default();
        let has = version::norm_ver(&latest) > version::norm_ver(&self.current);

        let mut download_url = String::new();
        // 优先精确匹配本工具（Rust 版）的 exe 名；未命中则退化为首个 .exe，
        // 兼容早期只有单一 exe 的发布。一个 release 挂了 Python / Rust 两个
        // exe，若不精确匹配可能下载错版本（对标 Python 版同名 bug 修复）。
        let want = "cnkicitationtool-rs.exe";
        if let (Some(rid), false) = (release.id, self.token.is_empty()) {
            let att_url = format!(
                "https://gitee.com/api/v5/repos/{}/{}/releases/{}/attach_files",
                self.owner, self.repo, rid
            );
            if let Ok(aresp) = ureq::get(&att_url)
                .timeout(Duration::from_secs(10))
                .query("access_token", &self.token)
                .call()
            {
                if let Ok(atts) = aresp.into_json::<Vec<Attachment>>() {
                    let mut fallback: Option<String> = None;
                    for a in atts {
                        if let (Some(n), Some(aid)) = (a.name, a.id) {
                            let lower = n.to_lowercase();
                            if !lower.ends_with(".exe") {
                                continue;
                            }
                            let url = format!(
                                "https://gitee.com/api/v5/repos/{}/{}/releases/{}/attach_files/{}/download?access_token={}",
                                self.owner, self.repo, rid, aid, self.token
                            );
                            if lower == want {
                                download_url = url;
                                break;
                            }
                            if fallback.is_none() {
                                fallback = Some(url);
                            }
                        }
                    }
                    if download_url.is_empty() {
                        download_url = fallback.unwrap_or_default();
                    }
                }
            }
        }

        Ok(UpdateInfo {
            has_update: has,
            latest,
            url: release.html_url.unwrap_or_default(),
            notes: release.body.unwrap_or_default(),
            download_url,
        })
    }
}

/// 把 `url` 指向的文件下载到 `dest`（用于自更新）。
///
/// 复用 ureq 的 TLS 配置（与 `check` 一致），默认跟随重定向。
/// 下载为阻塞式，调用方应在后台线程执行以免卡住 UI。
pub fn download(url: &str, dest: &Path) -> Result<(), String> {
    let resp = ureq::get(url)
        .timeout(Duration::from_secs(300))
        .call()
        .map_err(|e| format!("{e}"))?;
    let mut reader = resp.into_reader();
    let mut buf = Vec::new();
    reader
        .read_to_end(&mut buf)
        .map_err(|e| format!("读取下载流失败：{e}"))?;
    std::fs::write(dest, &buf).map_err(|e| format!("写入临时文件失败：{e}"))?;
    Ok(())
}
