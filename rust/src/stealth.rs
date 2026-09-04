//! 反自动化注入（对标 playwright-stealth 的核心覆盖）
//!
//! headless_chrome 自带 `enable_stealth_mode()`（一键隐藏 webdriver 等特征），
//! 这里额外保留一段最小必要 JS 作为补充。运行时不可验证，仅结构忠实。

/// 注入到每个新文档的 stealth 脚本（隐藏 webdriver 痕迹、规范化语言指纹）。
pub const STEALTH_JS: &str = r#"
(function () {
  try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
  } catch (e) {}
  try {
    if (!window.chrome) { window.chrome = {}; }
    if (!window.chrome.runtime) { window.chrome.runtime = {}; }
  } catch (e) {}
})();
"#;

#[cfg(feature = "browser")]
use headless_chrome::browser::tab::Tab;

/// 在 tab 上应用反自动化措施。任何一步失败只告警，不中断（效果由用户实机验证）。
#[cfg(feature = "browser")]
pub fn apply_stealth(tab: &Tab) {
    if let Err(e) = tab.enable_stealth_mode() {
        eprintln!("[stealth] enable_stealth_mode 失败: {e}");
    }
}
