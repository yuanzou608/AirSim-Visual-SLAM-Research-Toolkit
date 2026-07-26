import open3d as o3d
import numpy as np
from sklearn.neighbors import KDTree

# === 加载 point_cloud.ply（Photo-SLAM 输出）===
pcd_pred = o3d.io.read_point_cloud("point_cloud.ply")
pts_pred = np.asarray(pcd_pred.points)

# 改成：
if not pcd_pred.has_colors():
    print("⚠️ point_cloud.ply has no colors. Initialize with zeros.")
    colors_pred = np.zeros_like(pts_pred)
else:
    colors_pred = np.asarray(pcd_pred.colors)


# === 加载 semantic_frame_1.ply（GT 语义点）===
pcd_gt = o3d.io.read_point_cloud("semantic_frame_1.ply")
pts_gt = np.asarray(pcd_gt.points)
colors_gt = np.asarray(pcd_gt.colors)

# === 构建 KDTree：从 GT 点 → 高斯点最近邻匹配 ===
tree = KDTree(pts_pred)
dist, idx = tree.query(pts_gt, k=1)

# 初始化新颜色，复制原始 Photo-SLAM 点颜色
new_colors = colors_pred.copy()

# 将 GT 的颜色赋值给最邻近的高斯点
for i, pred_idx in enumerate(idx.flatten()):
    new_colors[pred_idx] = colors_gt[i]

# === 更新颜色并保存新点云 ===
pcd_pred.colors = o3d.utility.Vector3dVector(new_colors)
o3d.io.write_point_cloud("point_cloud_with_gt_semantic.ply", pcd_pred)

print("✅ 写入完成：point_cloud_with_gt_semantic.ply")
