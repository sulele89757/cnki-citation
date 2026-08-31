"""调试按钮高度：打印 CTkButton 实际渲染尺寸"""
import customtkinter as ctk
import sys

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.geometry("400x500")

results = []

def check():
    for name, btn in [("h=38", b38), ("h=46", b46), ("h=56", b56), ("batch", batch_btn)]:
        w = btn.winfo_width()
        h = btn.winfo_height()
        results.append(f"{name}: actual={w}x{h}")
    print("\n".join(results))
    with open("btn_debug.txt", "w") as f:
        f.write("\n".join(results))
    root.destroy()

# 测试各种高度
b38 = ctk.CTkButton(root, text="height=38 (浏览)", height=38)
b38.pack(fill="x", padx=20, pady=8)

b46 = ctk.CTkButton(root, text="height=46 (获取引文)", height=46)
b46.pack(fill="x", padx=20, pady=8)

b56 = ctk.CTkButton(root, text="height=56 (更粗)", height=56)
b56.pack(fill="x", padx=20, pady=8)

# 模拟批量区域的 frame + 按钮
frame = ctk.CTkFrame(root)
frame.pack(fill="x", padx=20, pady=8)
batch_btn = ctk.CTkButton(frame, text="开始批量处理 (frame内, h=46)", height=46)
batch_btn.pack(fill="x", padx=16, pady=(12, 16))

root.after(800, check)
root.mainloop()
