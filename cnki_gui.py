"""
CNKI 论文引文获取工具 — GUI 版本（CustomTkinter）
依赖：customtkinter, playwright, playwright-stealth, openpyxl
"""
import re
import webbrowser
import threading
import asyncio
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

import pystray
from PIL import Image, ImageDraw

import cnki_citation as core

APP_VERSION = core.APP_VERSION


class CNKIGui:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("CNKI 论文引文获取工具")
        self.root.geometry("840x760")
        self.root.minsize(740, 680)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        # ── 自定义配色覆盖（让界面不灰）──
        # 亮色模式：主色用更鲜亮的蓝；暗色模式保持深蓝
        self._colors = {
            # 主操作色（按钮/高亮）
            "primary":        ("#2563eb", "#3b82f6"),       # 亮蓝 / 稍亮蓝
            "primary_hover":  ("#1d4ed8", "#60a5fa"),
            "primary_text":   ("#ffffff", "#ffffff"),
            # 卡片背景
            "card_bg":        ("#ffffff", "#1e293b"),       # 白 / 深灰蓝
            "card_border":    ("#e2e8f0", "#334155"),
            # 输入框
            "entry_bg":       ("#f8fafc", "#0f172a"),
            "entry_border":   ("#cbd5e1", "#475569"),
            "entry_fg":       ("#1e293b", "#e2e8f0"),
            # 文字
            "text":           ("#0f172a", "#f1f5f9"),
            "text_secondary": ("#64748b", "#94a3b8"),
            "text_muted":     ("#94a3b8", "#64748b"),
            # 分段按钮
            "seg_unsel":      ("#e2e8f0", "#334155"),
            "seg_sel":        ("#2563eb", "#3b82f6"),
            "seg_unsel_text": ("#475569", "#94a3b8"),
            "seg_sel_text":   ("#ffffff", "#ffffff"),
            # 进度条
            "progress_bg":    ("#e2e8f0", "#334155"),
            "progress_fg":    ("#2563eb", "#3b82f6"),
            # 日志框
            "log_bg":         ("#f1f5f9", "#0f172a"),
            "log_text":       ("#334155", "#cbd5e1"),
            # 提示文字
            "hint_text":      ("#94a3b8", "#64748b"),
        }

        self._running = False
        self._tray_icon = None
        # 点 X 最小化到系统托盘，而非直接退出
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    # ───────────────────────── UI 构建 ─────────────────────────
    def _build(self):
        # 顶部标题
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 6))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="CNKI 论文引文获取工具",
                      font=ctk.CTkFont(size=23, weight="bold"),
                      text_color=self._colors["text"][0]).pack(anchor="w")
        ctk.CTkLabel(left, text="GB/T 7714-2025 格式引文 · 自动搜索 · 批量导出",
                      font=ctk.CTkFont(size=12),
                      text_color=self._colors["text_secondary"][0]).pack(anchor="w")
        ctk.CTkButton(header, text="检查更新", width=92, height=32,
                      fg_color=self._colors["primary"][0],
                      hover_color=self._colors["primary_hover"][0],
                      text_color="#ffffff",
                      command=lambda: self._check_update(silent=False)).pack(
            side="right", padx=(10, 0))

        # 模式切换（选中态用主色高亮，未选中用浅灰）
        self.mode = ctk.StringVar(value="single")
        seg = ctk.CTkSegmentedButton(
            self.root, values=["单篇", "批量(Excel)"],
            variable=self.mode, command=self._on_mode_change,
            font=ctk.CTkFont(size=13, weight="bold"),
            unselected_color=self._colors["seg_unsel"][0],
            selected_color=self._colors["seg_sel"][0],
            unselected_hover_color=self._colors["card_border"][0],
            selected_hover_color=self._colors["primary_hover"][0],
            text_color=self._colors["seg_unsel_text"][0],
            text_color_disabled=self._colors["text_muted"][0],
            fg_color="transparent",
            corner_radius=10, height=40)
        # 暗色模式也需设置（CTkSegmentedButton 不自动跟随 mode 切换配色）
        self._seg = seg
        seg.pack(fill="x", padx=22, pady=(6, 4))

        # 单篇区域
        self.single_frame = ctk.CTkFrame(self.root, fg_color=self._colors["card_bg"][0],
                                         border_color=self._colors["card_border"][0], border_width=1)
        self.single_frame.pack(fill="x", padx=22, pady=8)
        ctk.CTkLabel(self.single_frame, text="论文标题", font=ctk.CTkFont(weight="bold"),
                      text_color=self._colors["text"][0]).pack(
            anchor="w", padx=16, pady=(14, 4))
        self.title_entry = ctk.CTkEntry(
            self.single_frame, height=40,
            placeholder_text="如：新形势下企业财务管理信息化建设的途径探索",
            fg_color=self._colors["entry_bg"][0], border_color=self._colors["entry_border"][0],
            text_color=self._colors["entry_fg"][0])
        self.title_entry.pack(fill="x", padx=16, pady=(0, 12))
        self.single_btn = self._make_big_button(
            self.single_frame, "获取引文", self._on_single)
        self.single_btn.pack(fill="x", padx=16, pady=(0, 16))

        # 批量区域
        self.batch_frame = ctk.CTkFrame(self.root, fg_color=self._colors["card_bg"][0],
                                        border_color=self._colors["card_border"][0], border_width=1)
        ctk.CTkLabel(self.batch_frame, text="Excel 文件", font=ctk.CTkFont(weight="bold"),
                      text_color=self._colors["text"][0]).pack(
            anchor="w", padx=16, pady=(14, 4))
        row1 = ctk.CTkFrame(self.batch_frame, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=4)
        self.excel_entry = ctk.CTkEntry(row1, height=38, placeholder_text="选择 .xlsx 文件",
                                         fg_color=self._colors["entry_bg"][0],
                                         border_color=self._colors["entry_border"][0],
                                         text_color=self._colors["entry_fg"][0])
        self.excel_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(row1, text="浏览", width=86, height=38, command=self._pick_excel,
                      fg_color=self._colors["primary"][0], hover_color=self._colors["primary_hover"][0],
                      text_color="#ffffff").pack(side="right")

        row2 = ctk.CTkFrame(self.batch_frame, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row2, text="标题列", width=52, text_color=self._colors["text_secondary"][0]).pack(side="left")
        self.title_col = ctk.CTkEntry(row2, height=34, width=96,
                                       fg_color=self._colors["entry_bg"][0],
                                       border_color=self._colors["entry_border"][0],
                                       text_color=self._colors["entry_fg"][0])
        self.title_col.insert(0, "标题")
        self.title_col.pack(side="left", padx=6)
        ctk.CTkLabel(row2, text="引文列", width=52, text_color=self._colors["text_secondary"][0]).pack(side="left", padx=(14, 0))
        self.out_col = ctk.CTkEntry(row2, height=34, width=96,
                                     fg_color=self._colors["entry_bg"][0],
                                     border_color=self._colors["entry_border"][0],
                                     text_color=self._colors["entry_fg"][0])
        self.out_col.insert(0, "引文")
        self.out_col.pack(side="left", padx=6)

        note = ctk.CTkLabel(
            self.batch_frame,
            text="提示：引文列不存在时自动新建；已填行自动跳过（断点续传）；每条实时保存。",
            font=ctk.CTkFont(size=11), text_color=self._colors["hint_text"][0])
        note.pack(anchor="w", padx=16, pady=(4, 0))
        self.batch_btn = self._make_big_button(
            self.batch_frame, "开始批量处理", self._on_batch)
        self.batch_btn.pack(fill="x", padx=16, pady=(12, 16))

        # 选项区域
        opt = ctk.CTkFrame(self.root, fg_color=self._colors["card_bg"][0],
                           border_color=self._colors["card_border"][0], border_width=1)
        opt.pack(fill="x", padx=22, pady=6)
        self.human_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt, text="拟人模式（推荐，规避机器人校验）",
                        variable=self.human_var, font=ctk.CTkFont(size=12),
                        text_color=self._colors["text"][0]).pack(
            side="left", padx=16, pady=12)
        gap = ctk.CTkFrame(opt, fg_color="transparent")
        gap.pack(side="right", padx=16, pady=8)
        ctk.CTkLabel(gap, text="搜索间隔(秒)", font=ctk.CTkFont(size=12),
                     text_color=self._colors["text_secondary"][0]).pack(side="left")
        self.min_gap = ctk.CTkEntry(gap, width=50, height=32,
                                     fg_color=self._colors["entry_bg"][0],
                                     border_color=self._colors["entry_border"][0],
                                     text_color=self._colors["entry_fg"][0])
        self.min_gap.insert(0, "5")
        self.min_gap.pack(side="left", padx=5)
        ctk.CTkLabel(gap, text="~", text_color=self._colors["text_secondary"][0]).pack(side="left")
        self.max_gap = ctk.CTkEntry(gap, width=50, height=32,
                                     fg_color=self._colors["entry_bg"][0],
                                     border_color=self._colors["entry_border"][0],
                                     text_color=self._colors["entry_fg"][0])
        self.max_gap.insert(0, "12")
        self.max_gap.pack(side="left", padx=5)

        # 进度
        prog = ctk.CTkFrame(self.root, fg_color="transparent")
        prog.pack(fill="x", padx=22, pady=(6, 2))
        self.progress = ctk.CTkProgressBar(prog, height=16,
                                          progress_color=self._colors["progress_fg"][0],
                                          bar_color=self._colors["progress_bg"][0])
        self.progress.pack(fill="x", side="left", expand=True, padx=(0, 12))
        self.progress.set(0)
        self.status_label = ctk.CTkLabel(prog, text="就绪", width=72,
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color=self._colors["text"][0])
        self.status_label.pack(side="right")

        # 日志
        ctk.CTkLabel(self.root, text="运行日志", font=ctk.CTkFont(weight="bold"),
                      text_color=self._colors["text"][0]).pack(
            anchor="w", padx=22, pady=(10, 2))
        self.log_box = ctk.CTkTextbox(self.root, height=155, font=ctk.CTkFont(size=12), wrap="word",
                                      fg_color=self._colors["log_bg"][0],
                                      border_color=self._colors["card_border"][0],
                                      text_color=self._colors["log_text"][0])
        self.log_box.pack(fill="both", expand=True, padx=22, pady=(0, 8))
        self.log_box.configure(state="disabled")

        # 结果
        ctk.CTkLabel(self.root, text="最新引文（可复制）", font=ctk.CTkFont(weight="bold"),
                      text_color=self._colors["text"][0]).pack(
            anchor="w", padx=22, pady=(0, 2))
        self.result_box = ctk.CTkTextbox(self.root, height=64, font=ctk.CTkFont(size=13),
                                        fg_color=self._colors["log_bg"][0],
                                        border_color=self._colors["card_border"][0],
                                        text_color=self._colors["text"][0])
        self.result_box.pack(fill="x", padx=22, pady=(0, 16))

        self._on_mode_change(self.mode.get())

    # ───────────────────────── 交互逻辑 ─────────────────────────
    def _make_big_button(self, parent, text, command, height=52):
        """自定义大按钮：CTkFrame + 居中标签，高度绝对可控（绕过 CTkButton height 渲染 bug）"""
        c = self._colors
        btn = ctk.CTkFrame(parent, height=height, corner_radius=10,
                            fg_color=c["primary"], hover_color=c["primary_hover"],
                            cursor="hand2")
        lbl = ctk.CTkLabel(btn, text=text,
                             font=ctk.CTkFont(size=15, weight="bold"), text_color=c["primary_text"])
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        def _on_click(e):
            if btn.cget("state") != "disabled":
                command()

        def _on_enter(e):
            if btn.cget("state") != "disabled":
                btn.configure(fg_color=c["primary_hover"])

        def _on_leave(e):
            if btn.cget("state") != "disabled":
                btn.configure(fg_color=c["primary"])

        btn.bind("<Button-1>", _on_click)
        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        lbl.bind("<Button-1>", _on_click)
        # 存储 state 与颜色，供 _set_running 禁用/启用
        btn._normal_fg = c["primary"]
        btn._hover_fg = c["primary_hover"]
        btn._lbl = lbl
        return btn

    def _on_mode_change(self, mode):
        if mode == "单篇":
            self.single_frame.pack(fill="x", padx=22, pady=8)
            self.batch_frame.pack_forget()
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill="x", padx=22, pady=8)

    def _pick_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel 文件", "*.xlsx *.xls")])
        if path:
            self.excel_entry.delete(0, "end")
            self.excel_entry.insert(0, path)

    def _log(self, text):
        self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

        m = re.search(r"第 (\d+)/(\d+) 篇", text)
        if m:
            i, n = int(m.group(1)), int(m.group(2))
            self.progress.set(i / n if n else 0)
            self.status_label.configure(text=f"{i}/{n}")

        # 提取成功行 → 结果框
        if "[✓ 成功]" in text:
            citation = text.split("]", 1)[-1].strip()
            self.result_box.delete("0.0", "end")
            self.result_box.insert("0.0", citation)

    def _set_running(self, running):
        self._running = running
        c = self._colors
        disabled = ("#9ca3af", "#6b7280")  # 灰色
        normal = c["primary"]               # 蓝色
        color = disabled if running else normal
        for btn in (self.single_btn, self.batch_btn):
            btn.configure(fg_color=color, cursor="arrow" if running else "hand2")
            btn._lbl.configure(text_color="#ffffff" if running else c["primary_text"])
        self.status_label.configure(text="运行中" if running else "就绪",
                                   text_color=c["text"][0])

    def _run_async(self, coro_args: dict):
        if self._running:
            return
        self._set_running(True)
        self.progress.set(0)
        self.result_box.delete("0.0", "end")
        self._log("[系统] 任务启动，正在打开浏览器（首次可能需手动通过验证码）...")

        def worker():
            results = []
            try:
                results = asyncio.run(core.run(**coro_args, on_log=self._log)) or []
            except Exception as e:
                self._log(f"[错误] {e}")
            finally:
                self.root.after(0, self._on_done, results)

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, results):
        self._set_running(False)
        self.status_label.configure(text="完成")
        self.progress.set(1)
        if results:
            ok = sum(1 for r in results if r.get("success"))
            self._log(f"[系统] 处理完毕：成功 {ok}/{len(results)}")

    def _parse_gap(self):
        try:
            return float(self.min_gap.get()), float(self.max_gap.get())
        except ValueError:
            messagebox.showerror("错误", "搜索间隔需为数字")
            return None

    def _on_single(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入论文标题")
            return
        gap = self._parse_gap()
        if not gap:
            return
        self._run_async(dict(
            titles=[title], connect=False, cdp="http://localhost:9222",
            human=self.human_var.get(), out_prefix="citations",
            excel_path=None, title_col=self.title_col.get(),
            out_col=self.out_col.get(), min_gap=gap[0], max_gap=gap[1],
        ))

    def _on_batch(self):
        excel = self.excel_entry.get().strip()
        if not excel or not Path(excel).exists():
            messagebox.showwarning("提示", "请选择有效的 Excel 文件")
            return
        gap = self._parse_gap()
        if not gap:
            return
        self._run_async(dict(
            titles=[], connect=False, cdp="http://localhost:9222",
            human=self.human_var.get(), out_prefix="citations",
            excel_path=excel, title_col=self.title_col.get(),
            out_col=self.out_col.get(), min_gap=gap[0], max_gap=gap[1],
        ))

    def _check_update(self, silent=True):
        self._log(f"[更新] 正在检查新版本（当前 v{APP_VERSION}）...")

        def worker():
            res = core.check_update()
            self.root.after(0, self._on_update_result, res, silent)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, res, silent):
        if res.get("skipped"):
            self._log("[更新] 未配置 Gitee 仓库，跳过检测")
            return
        if res.get("error"):
            if not silent:
                messagebox.showwarning("检查更新失败", res["error"])
            self._log(f"[更新] 检测失败：{res['error']}")
            return
        if res.get("has_update"):
            self.status_label.configure(text="有新版本")
            self._log(f"[更新] 发现新版本 {res.get('latest')}！发布页：{res.get('url')}")
            ans = messagebox.askyesno(
                "发现新版本",
                f"当前版本：v{APP_VERSION}\n最新版本：{res.get('latest')}\n\n"
                f"是否打开发布页下载更新？")
            if ans and res.get("url"):
                webbrowser.open(res.get("url"))
        else:
            if not silent:
                messagebox.showinfo("检查更新", f"已是最新版本 v{APP_VERSION}")
            self._log("[更新] 已是最新版本")

    # ───────────────────────── 系统托盘 ─────────────────────────
    @staticmethod
    def _make_tray_icon() -> Image.Image:
        """代码生成的托盘图标（蓝色圆角方块 + 引号），不依赖外部文件"""
        s = 64
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([10, 10, 54, 54], radius=14, fill=(37, 99, 235, 255))
        w = (255, 255, 255, 255)
        d.line([26, 30, 26, 40], fill=w, width=5)
        d.line([26, 30, 34, 30], fill=w, width=5)
        d.line([40, 30, 40, 40], fill=w, width=5)
        d.line([40, 30, 48, 30], fill=w, width=5)
        return img

    def _on_close(self):
        """点 X：隐藏到托盘（不退出进程），任务进行中时也允许最小化"""
        self.root.withdraw()
        self._show_tray()

    def _show_tray(self):
        if self._tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._restore, default=True),
            pystray.MenuItem("退出", self._quit),
        )
        self._tray_icon = pystray.Icon(
            "CNKI引文工具", self._make_tray_icon(),
            "CNKI 论文引文获取工具", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _restore(self):
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.after(0, self.root.deiconify)

    def _quit(self):
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.after(2000, lambda: self._check_update(silent=True))
        self.root.mainloop()


if __name__ == "__main__":
    CNKIGui().run()
