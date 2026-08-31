"""生成 CNKI 引文工具图标 (app.ico)：蓝色圆角卡片 + 引号 + 引文线"""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 背景圆角卡片（CNKI 蓝）
def rr(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)

rr(d, [16, 16, 240, 240], 48, (37, 99, 235, 255))        # 主卡片
rr(d, [16, 16, 240, 240], 48, None)
# 顶部高光
rr(d, [16, 16, 240, 120], 48, (59, 130, 246, 255))

# 白色引号（左上）
q = (255, 255, 255, 255)
d.line([70, 96, 70, 140], fill=q, width=16, joint="curve")
d.line([70, 96, 104, 96], fill=q, width=16, joint="curve")
d.line([132, 96, 132, 140], fill=q, width=16, joint="curve")
d.line([132, 96, 166, 96], fill=q, width=16, joint="curve")

# 引文横线（底部）
bar = (203, 213, 225, 255)
for i, y in enumerate([170, 196, 222]):
    w = 150 - i * 28
    d.rounded_rectangle([60, y, 60 + w, y + 12], radius=6, fill=bar)

img.save("app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("app.ico written")
