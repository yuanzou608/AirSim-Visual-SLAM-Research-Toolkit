import os
from pathlib import Path
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

# ========== 配置 ==========
in_dir  = Path("/home/yuan/Downloads/gt_semantic")              # 输入文件夹
out_dir = Path("/home/yuan/Downloads/gt_semantic_colorbar")     # 输出文件夹
out_dir.mkdir(parents=True, exist_ok=True)

# 颜色与类别
unique_colors = [
    (0,   0,   0),      # background
    (0,   128, 0),      # bush
    (0,   128, 128),    # power
    (128, 0,   0),      # tree
    (128, 0,   128),    # furniture
    (128, 128, 0),      # car
    (128, 128, 128),    # sign
]
class_names = ["background", "bush", "power", "tree", "furniture", "car", "sign"]

# ========== colormap 定义 ==========
cmap = ListedColormap(np.array(unique_colors) / 255.0, name="sem_cmap")
bounds = np.arange(len(unique_colors) + 1) - 0.5
norm = BoundaryNorm(bounds, cmap.N)

# 映射颜色到索引
color_to_idx = {tuple(c): i for i, c in enumerate(unique_colors)}

def rgb_to_index_map(img_rgb: np.ndarray) -> np.ndarray:
    H, W, _ = img_rgb.shape
    idx_map = np.full((H, W), -1, dtype=np.int16)
    for rgb, idx in color_to_idx.items():
        mask = np.all(img_rgb == rgb, axis=-1)
        idx_map[mask] = idx
    unknown = (idx_map == -1).sum()
    if unknown > 0:
        print(f"[WARN] {unknown} unknown pixels set to 0")
        idx_map[idx_map == -1] = 0
    return idx_map

# ========== 批处理 ==========
files = [p for p in in_dir.iterdir() if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp"]]
files.sort()

for img_path in files:
    img = Image.open(img_path).convert("RGB")
    img_np = np.array(img, dtype=np.uint8)
    idx_map = rgb_to_index_map(img_np)

    # 绘制
    fig = plt.figure(figsize=(img.width / 100 + 1.2, img.height / 100), dpi=100)
    ax = fig.add_axes([0.00, 0.00, 0.85, 1.00])
    cax = fig.add_axes([0.88, 0.10, 0.04, 0.80])

    im = ax.imshow(idx_map, cmap=cmap, norm=norm)
    ax.axis("off")

    cb = plt.colorbar(im, cax=cax, ticks=np.arange(len(unique_colors)))
    cb.ax.set_yticklabels(class_names)
    cb.ax.tick_params(labelsize=8)

    out_path = out_dir / img_path.name
    plt.savefig(out_path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"[OK] {img_path.name} -> {out_path}")

print("[DONE] 所有图片处理完成。")
