import os
import shutil

src_dir = "/home/yuan/airsim/data/semantic"
dst_dir = "/home/yuan/airsim/data/semantic_id"

# 确保目标目录存在
os.makedirs(dst_dir, exist_ok=True)

# 获取所有 .png 文件并排序
files = sorted([f for f in os.listdir(src_dir) if f.endswith(".png")])

# 遍历并复制 + 重命名
for idx, filename in enumerate(files):
    src_path = os.path.join(src_dir, filename)
    dst_filename = f"{idx:06d}.png"
    dst_path = os.path.join(dst_dir, dst_filename)

    shutil.copy2(src_path, dst_path)  # 使用 copy2 保留原始时间戳
    print(f"Copied: {filename} -> {dst_filename}")
