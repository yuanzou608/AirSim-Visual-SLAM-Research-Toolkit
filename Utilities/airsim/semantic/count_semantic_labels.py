# airsim semantic calculate: https://microsoft.github.io/AirSim/image_apis/#segmentation
# template: https://github.com/microsoft/AirSim/blob/main/PythonClient/computer_vision/segmentation.py
import os
import cv2
import numpy as np

semantic_dir = "/home/yuan/dataset/my_data/building25fps/semantic"  # 替换成你的路径
label_set = set()

for fname in sorted(os.listdir(semantic_dir)):
    if not fname.endswith('.png'):
        continue

    img_path = os.path.join(semantic_dir, fname)
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)

    if img is None:
        print(f"跳过无法读取的图像: {img_path}")
        continue

    # 转为 RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    R = img_rgb[:, :, 0].astype(np.uint32)
    G = img_rgb[:, :, 1].astype(np.uint32)
    B = img_rgb[:, :, 2].astype(np.uint32)

    # 解码为语义 ID
    semantic_ids = R + G * 256 + B * 256 * 256

    # 更新总的 label 集合
    unique_ids = np.unique(semantic_ids)
    label_set.update(unique_ids.tolist())

print("语义标签总数:", len(label_set))
print("标签ID列表:", sorted(label_set))
