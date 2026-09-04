//! CNKI 论文引文获取工具 —— Rust 移植版核心库

pub mod behavior;
pub mod citation;
pub mod config;
pub mod excel;
pub mod stealth;
pub mod update;
pub mod version;

#[cfg(feature = "browser")]
pub mod browser;

pub use anyhow::Result;
