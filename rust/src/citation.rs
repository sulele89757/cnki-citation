//! GB/T 7714-2025 引文文本提取（纯逻辑，对标 Python `extract_citation` 的文本正则部分）
//!
//! CNKI 引用页把多种格式连在一起返回，GB/T 7714 片段位于
//! `格式引文` 与 `MLA格式引文` / `APA格式引文` / `知网研学` 之间。
//! 同时兜底匹配 `GB/T 7714-2025` 标题段与 `[1] ...` 列表段。

use lazy_static::lazy_static;
use regex::Regex;

lazy_static! {
    // 1) CNKI 特有：多种格式连在一起，GB/T 7714 在 "格式引文" 和 "MLA/APA/知网研学" 之间
    //    注意：Rust `regex` 不支持 look-ahead，用「必选终止符组（终止符或文末 \z）」替代 (?=...)
    static ref RE_FORMAT: Regex = Regex::new(
        r"(?s)格式引文\s*\[?\d+\]?\s*(.*?)(?:\s*MLA格式引文|\s*APA格式引文|\s*知网研学|\z)"
    ).unwrap();

    // 2) 显式 GB/T 7714-2025 标题段
    static ref RE_GBT: Regex = Regex::new(
        r"(?s)GB/T\s*7714[—\-–]?\s*2025[：:\s]*\n?(.*?)(?:\n\s*\n|\n[A-Za-z]{2,}\s*7714|\z)"
    ).unwrap();

    // 3) [1] 列表段
    static ref RE_LIST: Regex = Regex::new(r"(?s)\[1\]\s*(.*?)(?:\n\s*\[2\]|\z)").unwrap();

    // 收尾清理
    static ref RE_WS: Regex = Regex::new(r"\s+").unwrap();
    static ref RE_LEADING_NUM: Regex = Regex::new(r"^\[\d+\]\s*").unwrap();
}

/// 从引用页文本中提取 GB/T 7714-2025 引文。
/// 返回 `None` 表示未提取到有效内容（长度不足 25 视为无效，与 Python 一致）。
pub fn extract_citation(body: &str) -> Option<String> {
    for re in [&*RE_FORMAT, &*RE_GBT, &*RE_LIST] {
        if let Some(caps) = re.captures(body) {
            if let Some(m) = caps.get(1) {
                let candidate = m.as_str().trim();
                if candidate.len() > 25 {
                    return Some(clean(candidate));
                }
            }
        }
    }
    None
}

/// 清理：合并空白、去除开头的 `[n]` 序号。
fn clean(text: &str) -> String {
    let t = RE_WS.replace_all(text, " ").trim().to_string();
    RE_LEADING_NUM.replace(&t, "").trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_between_format_and_mla() {
        let body = concat!(
            "格式引文 [1]张三, 李四. 新形势下企业财务管理信息化建设途径研究[J]. ",
            "会计之友, 2020(12): 45-49. ",
            "MLA格式引文 Zhang S, Li S. ..."
        );
        let got = extract_citation(body).unwrap();
        assert!(got.contains("张三"), "got = {got}");
        assert!(got.contains("会计之友"), "got = {got}");
        assert!(!got.contains("MLA格式引文"), "got = {got}");
        assert!(!got.starts_with('['), "got = {got}");
    }

    #[test]
    fn extracts_explicit_gbt_section() {
        let body = "GB/T 7714-2025：\n王五. 某研究[J]. 期刊, 2021, 10(2): 1-10.\n\n下一个段落";
        let got = extract_citation(body).unwrap();
        assert!(got.contains("王五"), "got = {got}");
        assert!(got.contains("2021"), "got = {got}");
    }

    #[test]
    fn extracts_list_form() {
        let body = "[1]赵六. 标题[J]. 杂志, 2019(3): 12-15.\n[2]另一个作者...";
        let got = extract_citation(body).unwrap();
        assert!(got.contains("赵六"), "got = {got}");
        assert!(!got.contains("[2]"), "got = {got}");
    }

    #[test]
    fn returns_none_when_too_short() {
        assert_eq!(extract_citation("短文本"), None);
        assert_eq!(extract_citation(""), None);
    }

    #[test]
    fn collapses_whitespace() {
        let body = "格式引文 [1]作者.   标题\n\n[J].   期刊,   2020: 1-2. MLA格式引文 x";
        let got = extract_citation(body).unwrap();
        assert!(!got.contains("  "), "应无连续空格: {got}");
    }
}
