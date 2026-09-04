//! 拟人行为相关随机逻辑（对标 Python `HumanBehavior` 的间隔部分）
//!
//! 注：鼠标贝塞尔轨迹、逐字输入等需要浏览器实例，放在 `browser` 模块；
//! 这里只放与浏览器无关的纯随机间隔逻辑，便于单测。

use rand::Rng;

/// 两篇之间的随机间隔（秒），规避 CNKI 兜底速率校验。
/// 默认 5~12 秒（生产建议 ≥5s）。
pub fn random_gap(min_s: f64, max_s: f64) -> f64 {
    let mut rng = rand::thread_rng();
    rng.gen_range(min_s..=max_s)
}

/// 偶发长停顿：15% 概率额外 +3~8 秒，模拟真人翻页/思考。
/// 返回最终间隔秒数。
pub fn gap_with_possible_long_pause(min_s: f64, max_s: f64) -> f64 {
    let mut gap = random_gap(min_s, max_s);
    let mut rng = rand::thread_rng();
    if rng.gen_bool(0.15) {
        gap += rng.gen_range(3.0..=8.0);
    }
    gap
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gap_in_range() {
        for _ in 0..1000 {
            let g = random_gap(5.0, 12.0);
            assert!((5.0..=12.0).contains(&g), "gap out of range: {g}");
        }
    }

    #[test]
    fn long_pause_never_negative() {
        for _ in 0..1000 {
            let g = gap_with_possible_long_pause(5.0, 12.0);
            assert!(g >= 5.0, "gap too small: {g}");
        }
    }
}
