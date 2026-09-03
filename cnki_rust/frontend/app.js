/* ============================================================
   CNKI 引文工具 — 前端逻辑

   重要（踩坑记录）：window.__TAURI__ 的模块划分是
     T.core   → invoke / convertFileSrc / isTauri …（**没有 listen**）
     T.event  → listen / once / emit / emitTo
     T.window → getCurrentWindow / getAllWindows …
     T.dialog → 由 tauri-dialog.js（官方插件 IIFE）挂在 __TAURI__ 上，
                核心全局包里**不自带**。
   之前把 listen 从 T.core 里取，得到 undefined，第一次调用即抛错，
   导致后续所有 addEventListener 都没绑上 —— 表现为「按钮全部点不动」。
   ============================================================ */
(function () {
  "use strict";

  // ── Tauri 句柄（全部做空值兜底，任何一项缺失都不影响其余功能）──
  const T = window.__TAURI__ || {};
  const core = T.core || {};
  const evt = T.event || {};
  const win = T.window || {};

  const invoke = typeof core.invoke === "function" ? core.invoke : null;
  const listen = typeof evt.listen === "function" ? evt.listen : null;

  function currentWindow() {
    return typeof win.getCurrentWindow === "function" ? win.getCurrentWindow() : null;
  }

  // 对话框：优先官方插件；不可用时退回浏览器原生弹窗，绝不因它抛错
  const D = T.dialog || {};
  const dialog = {
    message:
      typeof D.message === "function"
        ? (m, o) => D.message(m, o)
        : async (m, o) => window.alert(o && o.title ? o.title + "\n\n" + m : m),
    ask:
      typeof D.ask === "function"
        ? (m, o) => D.ask(m, o)
        : async (m) => window.confirm(m),
    confirm:
      typeof D.confirm === "function"
        ? (m, o) => D.confirm(m, o)
        : async (m) => window.confirm(m),
    save: typeof D.save === "function" ? (o) => D.save(o) : async () => null,
    open: typeof D.open === "function" ? (o) => D.open(o) : async () => null,
  };

  let APP_VER = "1.0.4";
  let running = false;

  // ── DOM 速查 ──
  const $ = (id) => document.getElementById(id);
  const logBox = $("log-box");
  const progressFill = $("progress-fill");
  const statusEl = $("status");

  /** 安全绑定：元素不存在只警告，不中断整个脚本（这是旧版全崩的根因） */
  function on(id, type, fn) {
    const el = typeof id === "string" ? $(id) : id;
    if (!el) {
      console.warn("[CNKI] 元素不存在，跳过绑定：", id);
      return;
    }
    el.addEventListener(type, fn);
  }

  // ════════════════ 视图切换 ════════════════
  function switchView(v) {
    document
      .querySelectorAll(".nav-item")
      .forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    document
      .querySelectorAll(".view")
      .forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
    if (v === "settings") refreshHistory();
  }
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  // ════════════════ 标题栏 ════════════════
  on("btn-min", "click", () => {
    const w = currentWindow();
    if (w) w.minimize();
    else appendLog("[错误] 窗口句柄不可用，无法最小化");
  });
  on("btn-close", "click", () => {
    const w = currentWindow();
    if (w) w.hide(); // 隐藏到托盘，由 Rust 侧拦截 CloseRequested 兜底
    else window.close();
  });

  // ════════════════ 日志 / 进度 ════════════════
  function appendLog(text) {
    if (!logBox) return;
    const div = document.createElement("div");
    div.className = "line";
    const s = String(text);
    if (s.includes("[错误]") || s.includes("✗")) div.classList.add("line-error");
    else if (s.includes("[系统]") || s.includes("⚠")) div.classList.add("line-system");
    else if (s.includes("✓")) div.classList.add("line-success");
    div.textContent = s;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;

    const m = s.match(/第 (\d+)\/(\d+) 篇/);
    if (m) setProgress(parseInt(m[1], 10) / parseInt(m[2], 10));
  }
  function setProgress(p) {
    if (progressFill) progressFill.style.width = Math.max(0, Math.min(1, p)) * 100 + "%";
  }
  function setStatus(text, color) {
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = color || "var(--primary)";
    }
  }
  function setRunning(state) {
    running = state;
    onDisabled("btn-single", state);
    onDisabled("btn-batch", state);
    if (state) {
      setProgress(0);
      setStatus("▶ 运行中...", "var(--warning)");
    } else {
      setStatus("● 就绪");
    }
  }
  function onDisabled(id, disabled) {
    const el = $(id);
    if (el) el.disabled = !!disabled;
  }

  // 后端事件（invoke / listen 不可用时静默降级，不阻断 UI 绑定）
  if (listen) {
    listen("log", (e) => appendLog(e.payload));
    listen("run-state", (e) => setRunning(e.payload));
    listen("task-done", (e) => onTaskDone(e.payload));
  } else {
    appendLog("[错误] 未检测到 Tauri 事件 API，实时日志不可用");
  }

  function onTaskDone(res) {
    setProgress(1);
    setStatus("✓ 完成");
    if (res.mode === "single") {
      const rec = res.records && res.records[0];
      const box = $("single-result");
      box.textContent = "";
      if (rec && rec.success && rec.citation) {
        box.textContent = rec.citation;
        onDisabled("btn-copy", false);
        setStatus("✓ 已获取");
      } else {
        const err = rec ? rec.error || "未知错误" : "无结果";
        box.textContent =
          "✗ 获取失败：\n" +
          err +
          "\n\n可在下方运行日志查看详细过程，或重试（必要时按提示在浏览器中完成验证）。";
        onDisabled("btn-copy", true);
        setStatus("✗ 失败", "var(--danger)");
      }
    } else {
      const ok = (res.records || []).filter((r) => r.success).length;
      appendLog(`[系统] 处理完毕：成功 ${ok}/${(res.records || []).length}`);
    }
  }

  // ════════════════ 公共 ════════════════
  function getHuman() {
    const el = $("set-human");
    return el ? el.checked : true;
  }
  function parseGap() {
    const mn = parseFloat($("set-min-gap").value);
    const mx = parseFloat($("set-max-gap").value);
    if (isNaN(mn) || isNaN(mx)) {
      dialog.message("搜索间隔需为数字", { title: "错误" });
      return null;
    }
    return [mn, mx];
  }
  async function openPath(p) {
    if (!invoke) return;
    try {
      await invoke("open_path", { path: p });
    } catch (e) {
      appendLog("[错误] " + e);
    }
  }

  // ════════════════ 单篇 ════════════════
  on("btn-single", "click", async () => {
    if (!invoke) return appendLog("[错误] IPC 不可用（非 Tauri 环境）");
    const title = $("single-title").value.trim();
    if (!title) {
      dialog.message("请输入论文标题", { title: "提示" });
      return;
    }
    const gap = parseGap();
    if (!gap) return;

    const box = $("single-result");
    box.textContent = "获取中…";
    onDisabled("btn-copy", true);
    try {
      await invoke("start_single", {
        title,
        human: getHuman(),
        minGap: gap[0],
        maxGap: gap[1],
      });
    } catch (e) {
      appendLog("[错误] " + e);
      setRunning(false);
    }
  });

  on("btn-copy", "click", async () => {
    const text = $("single-result").textContent.trim();
    if (!text) return;
    const b = $("btn-copy");
    try {
      await navigator.clipboard.writeText(text);
      b.textContent = "✓ 已复制";
      setTimeout(() => (b.textContent = "一键复制"), 1500);
    } catch (e) {
      // WebView 里 clipboard API 可能被拒，退回 execCommand
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        b.textContent = "✓ 已复制";
        setTimeout(() => (b.textContent = "一键复制"), 1500);
      } catch (e2) {
        appendLog("[提示] 复制失败，请手动选中复制");
      }
    }
  });

  // ════════════════ 批量 ════════════════
  on("btn-template", "click", async () => {
    if (!invoke) return appendLog("[错误] IPC 不可用（非 Tauri 环境）");
    // defaultPath 必须是绝对路径：插件会把「相对且不存在的路径」当成目录，
    // 导致保存框没有默认文件名。
    let dir = "";
    try {
      dir = await invoke("default_save_dir");
    } catch (e) {
      /* 取不到就用空串，让系统自己决定初始目录 */
    }
    const defaultPath = dir ? dir + "\\批量引文模板.xlsx" : "批量引文模板.xlsx";
    try {
      const dest = await dialog.save({
        filters: [{ name: "Excel", extensions: ["xlsx"] }],
        defaultPath,
      });
      if (!dest) return;
      await invoke("download_template", { dest });
      appendLog("[系统] Excel 模板已保存到：" + dest);
      dialog.message(
        "模板已保存：\n" + dest + "\n\n使用说明：\n" +
          "• 「标题」列填写论文标题\n" +
          "• 「引文」列留空，程序会自动回填\n" +
          "• 完成后在上方「浏览」选择该文件即可批量处理",
        { title: "完成" }
      );
    } catch (e) {
      appendLog("[错误] " + e);
    }
  });

  on("btn-browse", "click", async () => {
    try {
      const sel = await dialog.open({
        filters: [{ name: "Excel", extensions: ["xlsx"] }],
        multiple: false,
      });
      if (sel) {
        const p = Array.isArray(sel) ? sel[0] : sel;
        $("batch-path").value = p;
      }
    } catch (e) {
      appendLog("[错误] " + e);
    }
  });

  on("btn-batch", "click", async () => {
    if (!invoke) return appendLog("[错误] IPC 不可用（非 Tauri 环境）");
    const excel = $("batch-path").value.trim();
    if (!excel) {
      dialog.message("请选择有效的 Excel 文件", { title: "提示" });
      return;
    }
    if (!/\.xlsx$/i.test(excel)) {
      dialog.message("仅支持 .xlsx 格式（.xls 旧格式请用 Excel/WPS 另存为 .xlsx）", {
        title: "提示",
      });
      return;
    }
    const gap = parseGap();
    if (!gap) return;
    try {
      await invoke("start_batch", {
        excelPath: excel,
        titleCol: $("batch-title-col").value.trim() || "标题",
        outCol: $("batch-out-col").value.trim() || "引文",
        human: getHuman(),
        minGap: gap[0],
        maxGap: gap[1],
      });
    } catch (e) {
      appendLog("[错误] " + e);
      setRunning(false);
    }
  });

  on("btn-open-output", "click", async () => {
    if (!invoke) return;
    try {
      await invoke("open_output");
    } catch (e) {
      appendLog("[错误] " + e);
    }
  });

  // ════════════════ 设置：更新 / 历史 ════════════════
  async function checkUpdate(silent) {
    if (!invoke) return;
    appendLog("[更新] 正在检查新版本...");
    try {
      const res = await invoke("check_update");
      if (!res || (!res.latest && !res.has_update)) {
        appendLog("[更新] 未配置仓库，跳过");
        if (!silent) dialog.message("未配置 Gitee 仓库，跳过检测", { title: "更新" });
        return;
      }
      if (res.has_update) {
        appendLog("[更新] 发现新版本 " + res.latest + "！");
        const ans = await dialog.ask(
          "当前版本：v" + APP_VER + "\n最新版本：" + res.latest + "\n\n是否打开下载页面？",
          { title: "发现新版本", okLabel: "打开", cancelLabel: "稍后" }
        );
        if (ans && res.url) await openPath(res.url);
      } else {
        appendLog("[更新] 已是最新版本");
        if (!silent) dialog.message("已是最新版本 v" + APP_VER, { title: "检查更新" });
      }
    } catch (e) {
      appendLog("[更新] 检测失败：" + e);
    }
  }
  on("btn-update", "click", () => checkUpdate(false));

  async function refreshHistory() {
    if (!invoke) return;
    try {
      const n = await invoke("history_count");
      const el = $("history-count");
      if (el) el.textContent = "历史输出：" + n + " 个文件";
    } catch (e) {
      /* 忽略 */
    }
  }
  on("btn-clean", "click", async () => {
    if (!invoke) return;
    try {
      const n = await invoke("history_count");
      const ans = await dialog.confirm(
        `将删除历史输出目录中的文件（共 ${n} 个）。\n此操作不可恢复，确定继续？`,
        { title: "清理历史记录" }
      );
      if (!ans) return;
      const removed = await invoke("clean_history");
      appendLog("[系统] 已删除 " + removed + " 个历史文件");
      dialog.message("已清理 " + removed + " 个历史文件。", { title: "清理完成" });
      refreshHistory();
    } catch (e) {
      appendLog("[错误] " + e);
    }
  });

  on("btn-log-clear", "click", () => {
    if (logBox) logBox.innerHTML = "";
  });

  // ════════════════ 系统主题跟随 ════════════════
  // Rust 侧读注册表 AppsUseLightTheme（比 WebView 的 prefers-color-scheme 更可靠，
  // 且能在程序运行时跟随系统切换），前端定时轮询并写入 <html data-theme>。
  let lastTheme = "";
  async function syncTheme() {
    if (!invoke) return;
    try {
      const t = await invoke("system_theme"); // "dark" | "light"
      if (t && t !== lastTheme) {
        lastTheme = t;
        document.documentElement.setAttribute("data-theme", t);
        const dot = document.querySelector(".brand-dot");
        if (dot) dot.style.display = "";
      }
    } catch (e) {
      /* 忽略：读不到就沿用 CSS 媒体查询的结果 */
    }
  }

  // ════════════════ 初始化 ════════════════
  (async () => {
    try {
      APP_VER = await invoke("get_version");
    } catch (e) {
      /* 忽略 */
    }
    const sv = $("sidebar-version");
    if (sv) sv.textContent = "v" + APP_VER;
    const ver = $("set-version");
    if (ver) ver.textContent = "当前版本 v" + APP_VER;
    refreshHistory();
    await syncTheme();
    setInterval(syncTheme, 2000); // 与 Python 版一致：持续跟随系统切换
    setTimeout(() => checkUpdate(true), 2500);
  })();

  // 兜底：任何未捕获异常都写进日志框，避免"静默全崩"再次发生
  window.addEventListener("error", (e) => {
    appendLog("[错误] JS 异常：" + (e.message || e));
  });
  window.addEventListener("unhandledrejection", (e) => {
    appendLog("[错误] 未处理的 Promise 拒绝：" + (e.reason && e.reason.message ? e.reason.message : e.reason));
  });
})();
