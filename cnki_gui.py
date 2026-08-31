"""
CNKI 论文引文获取工具 — GUI 版本（CustomTkinter，v4 设计师重构）
布局：左侧暗色导航 + 右侧内容区（单篇/批量/设置三视图）+ 底栏（进度+日志）
依赖：customtkinter, playwright, playwright-stealth, openpyxl, pystray, Pillow
"""
import os
import re
import sys
import shutil
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


# ── 单例锁：防止启动多个实例（Windows Mutex）──
def _check_singleton():
    """若已有实例在运行，弹出提示并退出。返回 True 表示可继续。"""
    try:
        import win32event
        import win32api
        import winerror
        _SINGLETON_MUTEX_NAME = "CNKI_Citation_Tool_Singleton_Mutex"
        handle = win32event.CreateMutex(None, False, _SINGLETON_MUTEX_NAME)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            # 已有实例：尝试激活其窗口后退出
            try:
                import win32gui
                hwnd = win32gui.FindWindow(None, "CNKI 引文工具")
                if hwnd:
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                    win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            # 用 tkinter 弹提示（此时 root 尚未创建，用简易弹窗）
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.after(100, lambda: (
                messagebox.showinfo("提示", "CNKI 引文工具已在运行中。\n"
                                     "请查看系统托盘或任务栏中的窗口。"),
                r.destroy()
            ))
            r.mainloop()
            return False
        return True
    except ImportError:
        # pywin32 不可用时（开发环境可能缺），跳过单例检查
        return True


class CNKIGui:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("CNKI 引文工具")
        self.root.geometry("780x680")
        self.root.minsize(680, 600)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self._mi = 0 if ctk.get_appearance_mode() == "Light" else 1

        # ── 配色 Token（亮 / 暗）──
        self.C = {
            # 侧边栏（始终暗色，保证图标/文字对比）
            "side_bg":        ("#1e2433", "#0d1117"),
            "side_text":      ("#cbd5e1", "#cbd5e1"),
            "side_sel":       ("#2b3447", "#161b22"),
            "side_hover":     ("#283142", "#11161d"),
            "side_accent":    ("#378ADD", "#388bfd"),
            "side_muted":     ("#7c8798", "#6e7681"),
            # 内容区
            "bg":             ("#f0f2f5", "#0f1117"),
            "card":           ("#ffffff", "#161b22"),
            "border":         ("#d0d5dd", "#30363d"),
            "border_light":   ("#e8ecf1", "#21262d"),
            "primary":        ("#1677ff", "#388bfd"),
            "primary_hover":  ("#0958d9", "#4da1ff"),
            "primary_text":   ("#ffffff", "#ffffff"),
            "text":           ("#1a1a2e", "#e6edf3"),
            "text_secondary": ("#595959", "#8b949e"),
            "text_muted":     ("#8c8c8c", "#6e7681"),
            "fill":           ("#f5f6fa", "#1c2128"),
            "fill_hover":     ("#ebedf0", "#262c36"),
            "prog_track":     ("#d9d9d9", "#30363d"),
            "prog_fill":      ("#1677ff", "#58a6ff"),
            "success":        ("#52c41a", "#4ade80"),
            "warning":        ("#faad14", "#fbbf24"),
        }

        self._running = False
        self._tray_icon = None
        self._nav = {}
        self._mode = "single"   # 当前任务模式：single / batch
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    # ════════════════════════════════════════════
    #  图标（PIL 线性图标，跨平台一致）
    # ════════════════════════════════════════════
    def _icon(self, kind, color=(203, 213, 225)):
        s = 32
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = color
        w = 2
        if kind == "doc":
            d.rounded_rectangle([9, 5, 23, 27], radius=3, outline=c, width=w)
            for y in (11, 16, 21):
                d.line([12, y, 20, y], fill=c, width=w)
        elif kind == "grid":
            for (x, y) in [(7, 7), (17, 7), (7, 17), (17, 17)]:
                d.rectangle([x, y, x + 8, y + 8], outline=c, width=w)
        elif kind == "sliders":
            d.line([10, 11, 22, 11], fill=c, width=w)
            d.ellipse([13, 9, 17, 13], fill=c)
            d.line([10, 21, 22, 21], fill=c, width=w)
            d.ellipse([13, 19, 17, 23], fill=c)
        elif kind == "brand":
            d.rounded_rectangle([6, 6, 26, 26], radius=7, fill=(22, 119, 255, 255))
            d.line([12, 12, 12, 20], fill=(255, 255, 255), width=2)
            d.line([12, 12, 17, 12], fill=(255, 255, 255), width=2)
            d.line([20, 12, 20, 20], fill=(255, 255, 255), width=2)
            d.line([20, 12, 25, 12], fill=(255, 255, 255), width=2)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(20, 20))

    # ════════════════════════════════════════════
    #  布局构建
    # ════════════════════════════════════════════
    def _build(self):
        C = self.C
        m = self._mi
        root = self.root
        root.configure(fg_color=C["bg"][m])

        # ═══ 左侧导航 ═══
        side = ctk.CTkFrame(root, width=200, fg_color=C["side_bg"][m],
                            corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        # 品牌
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(18, 8))
        ctk.CTkLabel(brand, text="", image=self._icon("brand")).pack(
            side="left", padx=(0, 10))
        ctk.CTkLabel(brand, text="CNKI 引文",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ffffff").pack(side="left")

        ctk.CTkLabel(side, text="工作模式",
                     font=ctk.CTkFont(size=10),
                     text_color=C["side_muted"][m]).pack(
            anchor="w", padx=18, pady=(14, 6))

        # 导航项
        for key, (label, icon) in {
            "single": ("单篇抓取", "doc"),
            "batch": ("批量处理", "grid"),
            "settings": ("设置", "sliders"),
        }.items():
            btn = ctk.CTkButton(
                side, text=label, image=self._icon(icon),
                compound="left", anchor="w",
                height=40, corner_radius=8,
                fg_color="transparent", hover_color=C["side_hover"][m],
                text_color=C["side_text"][m],
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self._select_nav(k))
            btn.pack(fill="x", padx=10, pady=3)
            self._nav[key] = btn

        # 底部版本号
        ctk.CTkLabel(side, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=10),
                     text_color=C["side_muted"][m]).pack(
            side="bottom", anchor="w", padx=18, pady=14)

        # ═══ 右侧内容区 ═══
        content = ctk.CTkFrame(root, fg_color=C["bg"][m], corner_radius=0)
        content.pack(side="left", fill="both", expand=True)

        # 视图容器（可切换）
        self.view_area = ctk.CTkFrame(content, fg_color="transparent")
        self.view_area.pack(fill="both", expand=True)

        self._build_single_view()
        self._build_batch_view()
        self._build_settings_view()

        # 底栏（进度 + 日志，常驻）
        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x", side="bottom")

        # 进度卡
        prog_card = ctk.CTkFrame(bottom, fg_color=C["card"][m],
                                 border_color=C["border"][m], border_width=1,
                                 corner_radius=12)
        prog_card.pack(fill="x", padx=20, pady=(0, 10))
        prog_inner = ctk.CTkFrame(prog_card, fg_color="transparent")
        prog_inner.pack(fill="x", padx=14, pady=10)
        self.progress = ctk.CTkProgressBar(
            prog_inner, height=8, corner_radius=4,
            fg_color=C["prog_track"][m],
            progress_color=C["prog_fill"][m])
        self.progress.pack(fill="x", side="left", expand=True, padx=(0, 12))
        self.progress.set(0)
        self.status_label = ctk.CTkLabel(
            prog_inner, text="● 就绪", width=80,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["primary"][m])
        self.status_label.pack(side="right")

        # 日志
        log_card = ctk.CTkFrame(bottom, fg_color=C["card"][m],
                                border_color=C["border"][m], border_width=1,
                                corner_radius=12)
        log_card.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkLabel(log_card, text="运行日志",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text_secondary"][m]).pack(
            anchor="w", padx=14, pady=(10, 4))
        self.log_box = ctk.CTkTextbox(
            log_card, height=110, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=C["fill"][m],
            border_width=0, corner_radius=8,
            text_color=C["text_secondary"][m])
        self.log_box.pack(fill="x", padx=14, pady=(0, 12))
        self.log_box.configure(state="disabled")

        self._select_nav("single")

    # ── 单篇视图 ──
    def _build_single_view(self):
        C, m = self.C, self._mi
        v = ctk.CTkFrame(self.view_area, fg_color="transparent")
        self.single_view = v

        inner = ctk.CTkFrame(v, fg_color=C["card"][m],
                             border_color=C["border"][m], border_width=1,
                             corner_radius=14)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(inner, text="单篇抓取",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(inner, text="输入论文标题，自动获取 GB/T 7714-2025 格式引文",
                     font=ctk.CTkFont(size=12),
                     text_color=C["text_secondary"][m]).pack(
            anchor="w", padx=20, pady=(0, 18))

        ctk.CTkLabel(inner, text="论文标题",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(0, 6))
        self.title_entry = ctk.CTkEntry(
            inner, height=42,
            placeholder_text="如：新形势下企业财务管理信息化建设的途径探索",
            fg_color=C["fill"][m],
            border_color=C["border_light"][m], border_width=1,
            corner_radius=9,
            text_color=C["text"][m],
            font=ctk.CTkFont(size=13))
        self.title_entry.pack(fill="x", padx=20, pady=(0, 18))

        self.single_btn = self._action_btn(inner, "获取引文", self._on_single)
        self.single_btn.pack(fill="x", padx=20, pady=(0, 16))

        # ── 结果区（直接显示在界面，支持一键复制）──
        ctk.CTkLabel(inner, text="获取结果",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(0, 6))

        result_card = ctk.CTkFrame(inner, fg_color=C["fill"][m],
                                   border_color=C["border_light"][m], border_width=1,
                                   corner_radius=10)
        result_card.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        self.single_result = ctk.CTkTextbox(
            result_card, height=120, font=ctk.CTkFont(size=13), wrap="word",
            fg_color="transparent", border_width=0, corner_radius=8,
            text_color=C["text"][m])
        self.single_result.pack(fill="both", expand=True, padx=12, pady=12)
        self.single_result.insert(
            "0.0", "点击「获取引文」后，结果将显示在此处，可直接复制使用。")
        self.single_result.configure(state="disabled")

        self.single_copy_btn = ctk.CTkButton(
            inner, text="一键复制", width=120, height=36,
            command=self._copy_single,
            fg_color=C["fill"][m], hover_color=C["border_light"][m],
            text_color=C["text"][m],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8, state="disabled")
        self.single_copy_btn.pack(anchor="e", padx=20, pady=(0, 16))

    # ── 批量视图 ──
    def _build_batch_view(self):
        C, m = self.C, self._mi
        v = ctk.CTkFrame(self.view_area, fg_color="transparent")
        self.batch_view = v

        inner = ctk.CTkFrame(v, fg_color=C["card"][m],
                             border_color=C["border"][m], border_width=1,
                             corner_radius=14)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(inner, text="批量处理",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(inner, text="选择 Excel 文件，按标题列批量获取并回填引文",
                     font=ctk.CTkFont(size=12),
                     text_color=C["text_secondary"][m]).pack(
            anchor="w", padx=20, pady=(0, 18))

        # 模板下载
        tpl_row = ctk.CTkFrame(inner, fg_color="transparent")
        tpl_row.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkButton(tpl_row, text="下载 Excel 模板", height=34, width=132,
                      command=self._download_template,
                      fg_color=C["fill"][m],
                      hover_color=C["border_light"][m],
                      text_color=C["primary"][m],
                      border_color=C["border_light"][m], border_width=1,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      corner_radius=8).pack(side="left")
        ctk.CTkLabel(tpl_row,
                     text="（含表头与一行示例：按「标题」列填论文，「引文」列留空）",
                     font=ctk.CTkFont(size=11),
                     text_color=C["text_muted"][m]).pack(
            side="left", padx=(10, 0))

        ctk.CTkLabel(inner, text="Excel 文件",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(0, 6))
        file_row = ctk.CTkFrame(inner, fg_color="transparent")
        file_row.pack(fill="x", padx=20, pady=(0, 14))
        self.excel_entry = ctk.CTkEntry(
            file_row, height=40,
            placeholder_text="选择包含论文标题的 .xlsx 文件",
            fg_color=C["fill"][m],
            border_color=C["border_light"][m], border_width=1,
            corner_radius=9,
            text_color=C["text"][m],
            font=ctk.CTkFont(size=13))
        self.excel_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(file_row, text="浏览", width=72, height=40,
                      command=self._pick_excel,
                      fg_color=C["primary"][m],
                      hover_color=C["primary_hover"][m],
                      text_color="#fff",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      corner_radius=9).pack(side="right")

        col_row = ctk.CTkFrame(inner, fg_color="transparent")
        col_row.pack(fill="x", padx=20, pady=(0, 12))
        for lbl, attr, default in [("标题列", "title_col", "标题"),
                                   ("引文列", "out_col", "引文")]:
            ctk.CTkLabel(col_row, text=lbl, width=46,
                         font=ctk.CTkFont(size=11),
                         text_color=C["text_secondary"][m]).pack(side="left")
            e = ctk.CTkEntry(col_row, height=32, width=90,
                             fg_color=C["fill"][m],
                             border_color=C["border_light"][m], border_width=1,
                             corner_radius=7,
                             text_color=C["text"][m],
                             font=ctk.CTkFont(size=12))
            e.insert(0, default)
            e.pack(side="left", padx=6)
            setattr(self, attr, e)
            if lbl == "标题列":
                ctk.CTkLabel(col_row, text="", width=12).pack(side="left")

        ctk.CTkLabel(inner,
                     text="引文列不存在时自动新建；已填行跳过；每条实时保存。",
                     font=ctk.CTkFont(size=11),
                     text_color=C["text_muted"][m]).pack(
            anchor="w", padx=20, pady=(0, 14))

        self.batch_btn = self._action_btn(inner, "开始批量处理", self._on_batch)
        self.batch_btn.pack(fill="x", padx=20, pady=(0, 20))

    # ── 设置视图 ──
    def _build_settings_view(self):
        C, m = self.C, self._mi
        v = ctk.CTkFrame(self.view_area, fg_color="transparent")
        self.settings_view = v

        inner = ctk.CTkFrame(v, fg_color=C["card"][m],
                             border_color=C["border"][m], border_width=1,
                             corner_radius=14)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(inner, text="设置",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"][m]).pack(
            anchor="w", padx=20, pady=(20, 14))

        self.human_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(inner, text="拟人模式（推荐，规避机器人校验）",
                        variable=self.human_var,
                        font=ctk.CTkFont(size=13),
                        text_color=C["text"][m],
                        checkbox_height=20, checkbox_width=20,
                        corner_radius=5).pack(
            anchor="w", padx=20, pady=(0, 16))

        gap_row = ctk.CTkFrame(inner, fg_color="transparent")
        gap_row.pack(anchor="w", padx=20, pady=(0, 16))
        ctk.CTkLabel(gap_row, text="搜索间隔（秒）",
                     font=ctk.CTkFont(size=13),
                     text_color=C["text"][m]).pack(side="left")
        for attr, w, d in [("min_gap", 50, "5"), ("max_gap", 50, "12")]:
            e = ctk.CTkEntry(gap_row, height=32, width=w,
                             fg_color=C["fill"][m],
                             border_color=C["border_light"][m], border_width=1,
                             corner_radius=7,
                             text_color=C["text"][m],
                             font=ctk.CTkFont(size=12))
            e.insert(0, d)
            e.pack(side="left", padx=6)
            setattr(self, attr, e)
            if attr == "min_gap":
                ctk.CTkLabel(gap_row, text="~",
                             text_color=C["text_secondary"][m]).pack(
                    side="left", padx=2)

        ctk.CTkButton(inner, text="检查更新",
                      command=lambda: self._check_update(silent=False),
                      fg_color=C["fill"][m],
                      hover_color=C["border_light"][m],
                      text_color=C["text"][m],
                      font=ctk.CTkFont(size=12, weight="bold"),
                      corner_radius=8, width=120, height=36).pack(
            anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(inner, text=f"当前版本 v{APP_VERSION}",
                     font=ctk.CTkFont(size=11),
                     text_color=C["text_muted"][m]).pack(
            anchor="w", padx=20, pady=(0, 20))

    # ════════════════════════════════════════════
    #  导航切换
    # ════════════════════════════════════════════
    def _select_nav(self, key):
        C, m = self.C, self._mi
        for k, btn in self._nav.items():
            if k == key:
                btn.configure(fg_color=C["side_sel"][m],
                              text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent",
                              text_color=C["side_text"][m])
        for view in (self.single_view, self.batch_view, self.settings_view):
            view.pack_forget()
        getattr(self, f"{key}_view").pack(fill="both", expand=True)

    # ════════════════════════════════════════════
    #  组件工厂
    # ════════════════════════════════════════════
    def _action_btn(self, parent, text, command, height=46):
        C, m = self.C, self._mi
        btn = ctk.CTkFrame(parent, height=height, corner_radius=10,
                           fg_color=C["primary"][m], cursor="hand2")
        btn.pack_propagate(False)
        lbl = ctk.CTkLabel(btn, text=text,
                           font=ctk.CTkFont(size=14, weight="bold"),
                           text_color=C["primary_text"][m])
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        def _click(e):
            if not getattr(btn, "_disabled", False):
                command()

        def _enter(e):
            if not getattr(btn, "_disabled", False):
                btn.configure(fg_color=C["primary_hover"][m])

        def _leave(e):
            if not getattr(btn, "_disabled", False):
                btn.configure(fg_color=C["primary"][m])

        for w in (btn, lbl):
            w.bind("<Button-1>", _click)
        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        btn._lbl = lbl
        btn._disabled = False
        return btn

    # ════════════════════════════════════════════
    #  交互逻辑
    # ════════════════════════════════════════════
    def _pick_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel 文件 (*.xlsx)", "*.xlsx")])
        if path:
            self.excel_entry.delete(0, "end")
            self.excel_entry.insert(0, path)

    def _get_template_path(self):
        name = "批量引文模板.xlsx"
        if getattr(sys, "frozen", False):
            return os.path.join(sys._MEIPASS, name)
        return os.path.join(Path(__file__).resolve().parent, name)

    def _download_template(self):
        src = self._get_template_path()
        if not os.path.exists(src):
            messagebox.showerror("模板缺失", f"未找到内置模板文件：\n{src}")
            return
        dst = filedialog.asksaveasfilename(
            title="保存 Excel 模板",
            initialdir=str(core.OUTPUT_DIR),
            initialfile="批量引文模板.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件 (*.xlsx)", "*.xlsx")])
        if not dst:
            return
        try:
            shutil.copyfile(src, dst)
        except Exception as e:
            messagebox.showerror("保存失败", f"模板保存失败：\n{e}")
            return
        self._log(f"[系统] Excel 模板已保存到：{dst}")
        messagebox.showinfo("完成",
            f"模板已保存：\n{dst}\n\n使用说明：\n"
            f"• 「标题」列填写论文标题\n"
            f"• 「引文」列留空，程序会自动回填\n"
            f"• 完成后在上方「浏览」选择该文件即可批量处理")

    def _log(self, text):
        self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

        mt = re.search(r"第 (\d+)/(\d+) 篇", text)
        if mt:
            i, n = int(mt.group(1)), int(mt.group(2))
            self.progress.set(i / n if n else 0)
            self.status_label.configure(text=f"{i}/{n}")
        if "[✓ 成功]" in text:
            citation = text.split("]", 1)[-1].strip()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "\n" + "─" * 38 + "\n")
            self.log_box.insert("end", f"★ 最新引文：\n{citation}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    def _set_running(self, running):
        self._running = running
        C, m = self.C, self._mi
        color = C["border"][m] if running else C["primary"][m]
        txt = C["text_muted"][m] if running else "#ffffff"
        for btn in (self.single_btn, self.batch_btn):
            btn._disabled = running
            btn.configure(fg_color=color)
            btn._lbl.configure(text_color=txt)
        self.status_label.configure(
            text="▶ 运行中..." if running else "● 就绪",
            text_color=C["warning"][m] if running else C["primary"][m])

    def _run_async(self, coro_args: dict):
        if self._running:
            return
        self._set_running(True)
        self.progress.set(0)
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
        self.status_label.configure(text="✓ 完成")
        self.progress.set(1)
        if not results:
            return
        if getattr(self, "_mode", "single") == "single":
            rec = results[0]
            self.single_result.configure(state="normal")
            self.single_result.delete("0.0", "end")
            if rec.get("success") and rec.get("citation"):
                self.single_result.insert("0.0", rec["citation"])
                self.single_copy_btn.configure(state="normal")
                self.status_label.configure(text="✓ 已获取")
            else:
                err = rec.get("error") or "未知错误"
                self.single_result.insert(
                    "0.0",
                    f"✗ 获取失败：\n{err}\n\n可在下方运行日志查看详细过程，"
                    f"或重试（必要时按提示在浏览器中完成验证）。")
                self.single_copy_btn.configure(state="disabled")
                self.status_label.configure(text="✗ 失败")
            self.single_result.configure(state="disabled")
        else:
            ok = sum(1 for r in results if r.get("success"))
            self._log(f"[系统] 处理完毕：成功 {ok}/{len(results)}")

    def _copy_single(self):
        """把单篇结果复制到剪贴板，并给出反馈"""
        text = self.single_result.get("0.0", "end").strip()
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except Exception:
            self._log("[提示] 复制失败，请手动选中文本复制")
            return
        C, m = self.C, self._mi
        self.single_copy_btn.configure(text="✓ 已复制", fg_color=C["success"][m],
                                       text_color="#ffffff")
        self.root.after(
            1500, lambda: self.single_copy_btn.configure(
                text="一键复制", fg_color=C["fill"][m],
                text_color=C["text"][m]))

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
        self._mode = "single"
        # 清空上次结果，禁用复制
        self.single_result.configure(state="normal")
        self.single_result.delete("0.0", "end")
        self.single_result.configure(state="disabled")
        self.single_copy_btn.configure(state="disabled")
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
        if not excel.lower().endswith((".xlsx", ".xlsm")):
            messagebox.showwarning(
                "提示",
                "仅支持 .xlsx 格式（.xls 旧格式不支持，请用 Excel/WPS 另存为 .xlsx）。\n"
                "本工具无需安装 Office，使用 openpyxl 直接读取。")
            return
        gap = self._parse_gap()
        if not gap:
            return
        self._mode = "batch"
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
            self.status_label.configure(text="↻ 有新版本")
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

    # ════════════════════════════════════════════
    #  系统托盘
    # ════════════════════════════════════════════
    @staticmethod
    def _make_tray_icon() -> Image.Image:
        s = 64
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([8, 8, 56, 56], radius=16, fill=(22, 119, 255, 255))
        w = (255, 255, 255, 255)
        d.line([24, 24, 24, 40], fill=w, width=5)
        d.line([24, 24, 34, 24], fill=w, width=5)
        d.line([40, 24, 40, 40], fill=w, width=5)
        d.line([40, 24, 50, 24], fill=w, width=5)
        return img

    def _on_close(self):
        # 点 X：仅隐藏窗口，托盘图标保持常驻（若意外未创建则补建）
        self.root.withdraw()
        if self._tray_icon is None:
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
        # 托盘常驻：仅恢复窗口，不销毁托盘图标
        self.root.after(0, self.root.deiconify)

    def _quit(self):
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.after(0, self.root.destroy)

    def run(self):
        # 启动时即在系统托盘常驻显示图标（窗口打开时也能看到）
        self._show_tray()
        self.root.after(2500, lambda: self._check_update(silent=True))
        self.root.mainloop()


if __name__ == "__main__":
    if _check_singleton():
        CNKIGui().run()
