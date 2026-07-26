import numpy as np
import cv2
import open3d as o3d
from scipy.spatial.transform import Rotation as R

# === 参数 ===
depth_path = "depth_1749400109.301154.png"
semantic_path = "semantic_1749400109.301154.png"
fx, fy = 336.0, 336.0
cx, cy = 336.0, 188.0

# 相机位姿：Tcw（世界坐标 → 相机坐标），你要换成你自己的
# 位姿字符串转为数值
t = np.array([-0.009006435, 0.006491568, -0.009022148])
q = np.array([0.000110923, 0.000141005, -0.000036089, 1.000000000])  # [x, y, z, w]

# 转为旋转矩阵
rotation = R.from_quat(q).as_matrix()  # shape (3, 3)

# 构造 Tcw（世界坐标 → 相机坐标）
Tcw = np.eye(4)
Tcw[:3, :3] = rotation
Tcw[:3, 3] = t

# 得到 Twc（相机坐标 → 世界坐标）用于反投影
Twc = np.linalg.inv(Tcw)


# === 加载图像 ===
depth_img = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED).astype(np.float32) / 1000 # m

# 加载彩色语义图（单位：uint8 RGB）
semantic_img = cv2.imread(semantic_path, cv2.IMREAD_COLOR)  # shape: H x W x 3
semantic_img = cv2.cvtColor(semantic_img, cv2.COLOR_BGR2RGB)  # 转换为 RGB

H, W = depth_img.shape
u, v = np.meshgrid(np.arange(W), np.arange(H))
z = depth_img
x = (u - cx) * z / fx
y = (v - cy) * z / fy

# === 有效点 ===
valid = (z > 0)
xyz_cam = np.stack([x, y, z], axis=-1)[valid]
labels = semantic_img[valid]

# === 变换到世界坐标 ===
T = np.linalg.inv(Tcw)  # 相机坐标 → 世界坐标
R, t = T[:3, :3], T[:3, 3]
xyz_world = (R @ xyz_cam.T + t.reshape(3, 1)).T

# 获取每个有效点的 RGB 语义颜色
colors = semantic_img[valid] / 255.0  # 归一化到 0~1

# === 构建点云 ===
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(xyz_world)
pcd.colors = o3d.utility.Vector3dVector(colors)

# === 保存 & 可视化 ===
o3d.io.write_point_cloud("semantic_frame_1.ply", pcd)
o3d.visualization.draw_geometries([pcd], window_name="Semantic Frame 1")
