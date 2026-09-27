import os
from PIL import Image, ImageDraw, ImageFont

root = "images"
categories = ["building", "house", "pool", "road", "roundabout"]

# 加大字体 80
FONT_SIZE = 50

try:
    font = ImageFont.truetype("DejaVuSans.ttf", FONT_SIZE)
except:
    font = ImageFont.load_default()

all_cols = []

for cat in categories:
    folder = os.path.join(root, cat)
    imgs = sorted([os.path.join(folder, f) for f in os.listdir(folder)
                   if f.lower().endswith((".png", ".jpg", ".jpeg"))])

    if len(imgs) != 6:
        print(f"[Error] {cat} 文件夹中图片数量不是 9 张！当前数量: {len(imgs)}")
        exit(1)

    pil_imgs = [Image.open(p) for p in imgs]
    all_cols.append((cat, pil_imgs))

# 所有图片 size
w, h = all_cols[0][1][0].size

# 留多一点空间给大字
label_h = int(FONT_SIZE * 1.5)

W = w * 5
H = h * 6 + label_h

canvas = Image.new("RGB", (W, H), (255, 255, 255))
draw = ImageDraw.Draw(canvas)

def get_text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)  # left, top, right, bottom
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height

# 拼接图像 + 大字体标签
for col_idx, (cat, imgs) in enumerate(all_cols):
    for row in range(6):
        x = col_idx * w
        y = row * h
        canvas.paste(imgs[row], (x, y))

    # 底部标签
    text = cat
    tw, th = get_text_size(draw, text, font)
    tx = col_idx * w + (w - tw) // 2
    ty = 6 * h + (label_h - th) // 2
    draw.text((tx, ty), text, fill=(0, 0, 0), font=font)

canvas.save("combined_9x5.png")
print("Saved combined_9x5.png")
