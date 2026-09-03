//! Gitee Releases 更新检测（对标 Python `check_update`）

use crate::version;
use serde::Deserialize;
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
                    for a in atts {
                        if let (Some(n), Some(aid)) = (a.name, a.id) {
                            if n.to_lowercase().ends_with(".exe") {
                                download_url = format!(
                                    "https://gitee.com/api/v5/repos/{}/{}/releases/{}/attach_files/{}/download?access_token={}",
                                    self.owner, self.repo, rid, aid, self.token
                                );
                                break;
                            }
                        }
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
