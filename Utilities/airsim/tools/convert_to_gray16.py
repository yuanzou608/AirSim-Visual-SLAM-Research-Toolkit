#!/usr/bin/env python3
"""
批量将 RGB PNG 转换为 16-bit 灰度 PNG，并重命名为 000000.png, 000001.png, ...
适用于 DSO / LSD-SLAM 等光度法算法。
"""

import cv2
import numpy as np
import os
import glob
from tqdm import tqdm

# ========== 修改路径 ========== #
input_folder  = "/home/yuan/data2tb/dataset/my_data/road25fps/rgb"
output_folder = "/home/yuan/data2tb/dataset/my_data/road25fps/rgb_gray16"
# ============================== #

os.makedirs(output_folder, exist_ok=True)

# 获取所有 png 文件并按名称排序
image_files = sorted(glob.glob(os.path.join(input_folder, "*.png")))
print(f"Found {len(image_files)} input images in {input_folder}")

for idx, img_path in enumerate(tqdm(image_files, desc="Converting")):
    # 读取为彩色图
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"⚠️  Skipped unreadable file: {img_path}")
        continue

    # 如果是三通道，则转换为灰度
    if len(img.shape) == 3:
        gray8 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray8 = img

    # 转换为 16-bit 灰度，线性放大：0-255 → 0-65535
    gray16 = (gray8.astype(np.uint16) * 257)

    # 生成新文件名，例如 000000.png
    new_name = f"{idx:06d}.png"
    out_path = os.path.join(output_folder, new_name)

    # 保存为 16-bit PNG
    cv2.imwrite(out_path, gray16)

print(f"\n✅ Done! Converted {len(image_files)} images saved to:\n{output_folder}")
