#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNKI 引文工具图标生成器
======================
按尺寸分级绘制，避免小帧直接下采样导致任务栏/标题栏图标发糊。

设计策略
--------
- 16/20/24/32：去掉手写「知」（该尺寸无法辨认），保留白/深灰底 + 粗橙色圆角外框，
  确保任务栏（常见 24/32）和标题栏（常见 16/24）边缘清晰、颜色鲜明。
- 40/48/64/128/256：完整品牌图标，含手写体「知」；尺寸越小相对边框越粗、字越大，
  以补偿细线字体在小尺寸下的衰减。

运行
----
    cd assets
    python generate_icons.py
"""
from __future__ import annotations

import io
import shutil
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# ── 品牌色 ──
ORANGE = "#FF873F"
WHITE = "#FFFFFF"
DARK_GRAY = "#1E1E1E"
BLACK = "#000000"

# 目标 ICO 帧（按 Windows 建议覆盖 16/24/32/48/256，并补充常用中间尺寸）
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
PNG_SIZE = 512

# 每帧参数（均为相对于画布边长的比例，最终取 max(最小像素, 计算值)）
SIZE_CONFIG: dict[int, dict] = {
    # 小尺寸：无文字，加粗边框，保证像素级清晰
    16:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.19, "font_pct": 0.00, "with_text": False},
    20:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.16, "font_pct": 0.00, "with_text": False},
    24:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.14, "font_pct": 0.00, "with_text": False},
    32:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.11, "font_pct": 0.00, "with_text": False},
    # 中等尺寸：引入手写「知」，相对加粗以提升可读性
    40:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.10, "font_pct": 0.60, "with_text": True},
    48:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.09, "font_pct": 0.60, "with_text": True},
    64:  {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.08, "font_pct": 0.60, "with_text": True},
    # 大尺寸：接近原始 SVG 比例（38/512 ≈ 0.074，300/512 ≈ 0.586）
    128: {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.075, "font_pct": 0.586, "with_text": True},
    256: {"margin_pct": 0.06, "radius_pct": 0.22, "border_min": 3, "border_pct": 0.074, "font_pct": 0.586, "with_text": True},
    # 512 PNG 源图：完全复刻 SVG 原始比例
    512: {"margin_pct": 0.0605, "radius_pct": 0.2207, "border_min": 38, "border_pct": 0.0742, "font_pct": 0.586, "with_text": True},
}


def _find_font() -> Path:
    """定位手写体（华文行楷），找不到则退回到楷体/宋体。"""
    candidates = [
        Path(r"C:\Windows\Fonts\STXINGKA.TTF"),
        Path(r"C:\Windows\Fonts\stxingka.ttf"),
        Path(r"C:\Windows\Fonts\SIMKAI.ttf"),
        Path(r"C:\Windows\Fonts\simkai.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("未找到可用的中文字体（华文行楷/楷体/宋体）")


FONT_PATH = _find_font()


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (255,)


def save_ico(frames: list[Image.Image], path: Path) -> None:
    """
    手写多帧 ICO 写入器。

    Pillow 的 ICO save 只支持从单图下采样生成各帧（会导致小帧发糊），
    不支持为每帧传入自定义内容。此函数按 Windows ICO 格式直接组装，
    每帧用 PNG 编码，完整保留我们逐个尺寸绘制的内容。
    """
    png_bytes: list[bytes] = []
    for im in frames:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        png_bytes.append(buf.getvalue())

    count = len(frames)
    # ICONDIR: Reserved(2) + Type(2) + Count(2)
    header = struct.pack("<HHH", 0, 1, count)

    # 计算数据偏移：header(6) + ICONDIRENTRY(16) * count
    offset = 6 + 16 * count
    entries: list[bytes] = []
    for im, data in zip(frames, png_bytes):
        w, h = im.size
        # ICO 目录里 0 表示 256
        bw = w if w < 256 else 0
        bh = h if h < 256 else 0
        entries.append(struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, len(data), offset))
        offset += len(data)

    with open(path, "wb") as f:
        f.write(header)
        for e in entries:
            f.write(e)
        for data in png_bytes:
            f.write(data)


def render_frame(
    size: int,
    bg_color: str,
    text_color: str,
    border_color: str,
) -> Image.Image:
    """绘制单帧图标，返回 RGBA 图像。"""
    cfg = SIZE_CONFIG[size]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, round(size * cfg["margin_pct"]))
    radius = max(2, round(size * cfg["radius_pct"]))
    border_w = max(cfg["border_min"], round(size * cfg["border_pct"]))
    x0, y0 = margin, margin
    x1, y1 = size - margin, size - margin

    # 底色块（不透明圆角矩形）
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=_hex_to_rgba(bg_color),
    )
    # 橙色外框
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        outline=_hex_to_rgba(border_color),
        width=border_w,
    )

    if cfg["with_text"]:
        font_size = max(8, round(size * cfg["font_pct"]))
        font = ImageFont.truetype(str(FONT_PATH), font_size)
        text = "知"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) / 2 - bbox[0]
        ty = (size - th) / 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=_hex_to_rgba(text_color))

    return img


def build_set(name: str, bg: str, text: str, border: str = ORANGE) -> None:
    """生成一套（亮色或暗色）的 PNG 与 ICO。"""
    # 512 PNG：供运行时托盘/CTkImage 缩放源，保持完整设计
    png = render_frame(PNG_SIZE, bg, text, border)
    png_path = HERE / f"{name}.png"
    png.save(png_path, "PNG")
    print(f"[生成] {png_path.name} ({PNG_SIZE}x{PNG_SIZE})")

    # 多帧 ICO：按尺寸分级绘制，保证每帧清晰
    frames: list[Image.Image] = []
    for s in ICO_SIZES:
        frames.append(render_frame(s, bg, text, border))
        print(f"  -> 帧 {s}x{s}: text={SIZE_CONFIG[s]['with_text']}, "
              f"border={max(SIZE_CONFIG[s]['border_min'], round(s * SIZE_CONFIG[s]['border_pct']))}px")

    ico_path = HERE / f"{name}.ico"
    save_ico(frames, ico_path)
    print(f"[生成] {ico_path.name} ({len(frames)} 帧)")


def main() -> int:
    print(f"字体: {FONT_PATH}")
    build_set("cnki_icon", bg=WHITE, text=BLACK)
    build_set("cnki_icon_dark", bg=DARK_GRAY, text=WHITE)

    # app.ico 与亮色图标保持一致（PyInstaller --icon 用它作为 EXE 文件图标）
    app_ico_src = HERE / "cnki_icon.ico"
    app_ico_dst = HERE / "app.ico"
    shutil.copy2(app_ico_src, app_ico_dst)
    print(f"[复制] {app_ico_src.name} -> {app_ico_dst.name}")

    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
