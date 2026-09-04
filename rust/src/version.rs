//! 版本号规整与比较（对标 Python `_norm_ver`）
//!
//! 把 `v1.0.1` / `1.0` / `2` 规整成 (主, 次, 修订) 三元组便于比较。

use lazy_static::lazy_static;
use regex::Regex;

lazy_static! {
    static ref RE_NUM: Regex = Regex::new(r"\d+").unwrap();
}

/// 规整为 (主, 次, 修订) 三元组，不足补 0。
pub fn norm_ver(v: &str) -> (u32, u32, u32) {
    let nums: Vec<u32> = RE_NUM
        .find_iter(v)
        .filter_map(|m| m.as_str().parse().ok())
        .collect();
    let mut padded = [0u32; 3];
    for (i, n) in nums.into_iter().take(3).enumerate() {
        padded[i] = n;
    }
    (padded[0], padded[1], padded[2])
}

/// `latest > current` 则返回 true（有更新）。
pub fn has_update(latest: &str, current: &str) -> bool {
    norm_ver(latest) > norm_ver(current)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn norm_handles_prefix_v() {
        assert_eq!(norm_ver("v1.0.1"), (1, 0, 1));
    }

    #[test]
    fn norm_pads_short() {
        assert_eq!(norm_ver("1.0"), (1, 0, 0));
        assert_eq!(norm_ver("2"), (2, 0, 0));
        assert_eq!(norm_ver("v3.2"), (3, 2, 0));
    }

    #[test]
    fn comparison_works() {
        assert!(has_update("v1.0.2", "1.0.1"));
        assert!(has_update("v2.0.0", "1.9.9"));
        assert!(!has_update("v1.0.0", "1.0.0"));
        assert!(!has_update("1.0.0", "v1.0.1"));
    }
}
