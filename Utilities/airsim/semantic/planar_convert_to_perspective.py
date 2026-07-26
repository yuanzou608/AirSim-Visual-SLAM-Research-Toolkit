import os
import cv2
import numpy as np
from tqdm import tqdm

# 相机内参（你已提供）
fx = 336.0
fy = 336.0
cx = 336.0
cy = 188.0

# 输入输出路径
# <<<<<<< HEAD
input_dir = "/home/yuan/airsim/data/depth_planar"
output_dir = "/home/yuan/airsim/data/depth"
# =======
input_dir = "/home/yuan/airsim/data/depth"
output_dir = "/home/yuan/airsim/data/depth_perspective"
# >>>>>>> origin/main
os.makedirs(output_dir, exist_ok=True)

def planar_to_perspective(depth_planar, fx, fy, cx, cy):
    height, width = depth_planar.shape
    u, v = np.meshgrid(np.arange(width), np.arange(height))
    x = (u - cx) / fx
    y = (v - cy) / fy
    factor = np.sqrt(1 + x**2 + y**2)
    return depth_planar * factor

# 遍历所有 PNG 文件
file_list = sorted([f for f in os.listdir(input_dir) if f.endswith(".png")])

print(f"Converting {len(file_list)} images from planar to perspective...")

for fname in tqdm(file_list):
    input_path = os.path.join(input_dir, fname)
    output_path = os.path.join(output_dir, fname)

    # 读取 uint16 深度图（单位：毫米）
    depth_mm = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)

    if depth_mm is None or depth_mm.dtype != np.uint16:
        print(f"Skipping {fname}: invalid or empty image")
        continue

    # 转为米
    depth_m = depth_mm.astype(np.float32) / 1000.0

    # 转换为 perspective 深度
    depth_persp_m = planar_to_perspective(depth_m, fx, fy, cx, cy)

    # 转换回 mm
    depth_persp_mm = (depth_persp_m * 1000.0).astype(np.uint16)

    # 保存图像
    cv2.imwrite(output_path, depth_persp_mm)

print("✅ Done! All perspective depth maps saved to:", output_dir)
