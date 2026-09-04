//! Excel 标题列解析 + 引文回填（对标 Python `load_excel` / 断点续传 / 实时保存）
//!
//! 使用 `umya-spreadsheet`（读 + 改 + 存，对标 openpyxl）。

use std::path::{Path, PathBuf};

use umya_spreadsheet::Spreadsheet;

/// 解析后的 Excel 任务集合。
pub struct ExcelTasks {
    pub book: Spreadsheet,
    pub title_idx: u32,
    pub out_idx: u32,
    /// (行号 1-based, 标题)
    pub tasks: Vec<(u32, String)>,
    pub path: PathBuf,
}

/// 解析列引用：字母(A/B/C) / 数字(1-based) / 列名(按表头查找)。
fn resolve_col(book: &Spreadsheet, spec: &str) -> anyhow::Result<u32> {
    let spec = spec.trim();
    if !spec.is_empty() && spec.chars().all(|c| c.is_ascii_alphabetic()) {
        return Ok(umya_spreadsheet::helper::coordinate::column_index_from_string(
            spec.to_uppercase().as_str(),
        ));
    }
    if let Ok(n) = spec.parse::<u32>() {
        return Ok(n);
    }
    if let Ok(ws) = book.get_sheet(&0) {
        let maxc = ws.get_highest_column();
        for c in 1..=maxc {
            if let Some(cell) = ws.get_cell((c, 1)) {
                if cell.get_value().trim() == spec {
                    return Ok(c);
                }
            }
        }
    }
    anyhow::bail!("未找到列：{spec}")
}

/// 加载 Excel，返回任务列表；若引文列不存在则自动新建（追加列 + 写表头）。
pub fn load_excel(path: &Path, title_col: &str, out_col: &str) -> anyhow::Result<ExcelTasks> {
    let mut book = umya_spreadsheet::reader::xlsx::read(path)
        .map_err(|e| anyhow::anyhow!("无法读取 Excel「{}」：{e}", path.display()))?;

    let title_idx = resolve_col(&book, title_col)?;
    let out_idx = match resolve_col(&book, out_col) {
        Ok(i) => i,
        Err(_) => {
            let maxc = book
                .get_sheet(&0)
                .map(|s| s.get_highest_column())
                .unwrap_or(0);
            let newc = maxc + 1;
            if let Ok(ws) = book.get_sheet_mut(&0) {
                ws.get_cell_mut((newc, 1)).set_value(out_col);
            }
            newc
        }
    };

    let mut tasks = Vec::new();
    if let Ok(ws) = book.get_sheet(&0) {
        let maxr = ws.get_highest_row();
        for r in 2..=maxr {
            if let Some(cell) = ws.get_cell((title_idx, r)) {
                let raw = cell.get_value();
                let v = raw.trim();
                if !v.is_empty() {
                    tasks.push((r, v.to_string()));
                }
            }
        }
    }

    Ok(ExcelTasks {
        book,
        title_idx,
        out_idx,
        tasks,
        path: path.to_path_buf(),
    })
}

/// 回填某行引文并立即保存到磁盘（对标 Python 实时 `wb.save`）。
/// 已存在的行由调用方判断跳过（断点续传）。
pub fn backfill(tasks: &mut ExcelTasks, row: u32, citation: &str) -> anyhow::Result<()> {
    if let Ok(ws) = tasks.book.get_sheet_mut(&0) {
        ws.get_cell_mut((tasks.out_idx, row)).set_value(citation);
    }
    umya_spreadsheet::writer::xlsx::write(&tasks.book, &tasks.path)?;
    Ok(())
}
