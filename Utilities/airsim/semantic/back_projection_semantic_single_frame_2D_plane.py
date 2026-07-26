import numpy as np
import cv2

# ------------------- 配置文件 --------------------
depth_file = "depth_1749400109.301154.png"
semantic_file = "semantic_1749400109.301154.png"
render_file = "rgb_1749400109.301154.png"
trajectory_file = "KeyFrameTrajectory_TUM.txt"

semantic_pose_ts = '1749400108.953514'  # 采集semantic的timestamp
render_pose_ts = '1749400108.953514'    # render RGB的timestamp

# 相机内参
fx, fy, cx, cy = 336.0, 336.0, 336.0, 188.0
intrinsic = np.array([[fx, 0, cx],
                      [0, fy, cy],
                      [0,  0,  1]])

# ------------------- 读取数据 --------------------
# 读取深度 (单位: 米)
depth = cv2.imread(depth_file, cv2.IMREAD_UNCHANGED).astype(np.float32) / 1000

# 读取 AirSim 彩色语义图，并解码为真实 label ID
semantic_rgb = cv2.imread(semantic_file, cv2.IMREAD_UNCHANGED)
semantic_rgb = cv2.cvtColor(semantic_rgb, cv2.COLOR_BGR2RGB)
semantic_label = semantic_rgb[:, :, 0] + semantic_rgb[:, :, 1] * 256 + semantic_rgb[:, :, 2] * 256 * 256
semantic_label = semantic_label.astype(np.uint32)

# 读取 render RGB
rgb_render = cv2.imread(render_file)

H, W = depth.shape

# ------------------- 读取pose文件 --------------------
def load_poses(file_path):
    poses = {}
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            ts, tx, ty, tz, qx, qy, qz, qw = map(float, line.strip().split())
            R = np.array([
                [1 - 2*qy**2 - 2*qz**2, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
                [2*qx*qy + 2*qz*qw, 1 - 2*qx**2 - 2*qz**2, 2*qy*qz - 2*qx*qw],
                [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx**2 - 2*qy**2]
            ])
            Tcw = np.eye(4)
            Tcw[:3, :3] = R
            Tcw[:3, 3] = [tx, ty, tz]
            poses[str(round(ts, 6))] = Tcw
    return poses

poses = load_poses(trajectory_file)

pose_semantic = poses[semantic_pose_ts]
pose_render = poses[render_pose_ts]

# ------------------- 反投影回3D点云 --------------------
i, j = np.meshgrid(np.arange(W), np.arange(H))
x = (i - cx) / fx
y = (j - cy) / fy
z = depth
X = x * z
Y = y * z
Z = z

points_cam = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
labels = semantic_label.reshape(-1)

# 加齐次
points_cam_hom = np.hstack([points_cam, np.ones((points_cam.shape[0], 1))])

# 先从semantic相机坐标系 -> 世界坐标系
points_world = (np.linalg.inv(pose_semantic) @ points_cam_hom.T).T

# 再从世界坐标系 -> render相机坐标系
points_render_cam = (pose_render @ points_world.T).T[:, :3]

# ------------------- 投影到render RGB图像 --------------------
Xr, Yr, Zr = points_render_cam[:, 0], points_render_cam[:, 1], points_render_cam[:, 2]

valid_z = Zr > 0
Xr_valid = Xr[valid_z]
Yr_valid = Yr[valid_z]
Zr_valid = Zr[valid_z]
labels_valid = labels[valid_z]

u = (fx * Xr_valid / Zr_valid + cx).astype(np.int32)
v = (fy * Yr_valid / Zr_valid + cy).astype(np.int32)

valid_uv = (u >= 0) & (u < W) & (v >= 0) & (v < H)
u, v, semantic_proj = u[valid_uv], v[valid_uv], labels_valid[valid_uv]

# ------------------- 生成最终投影semantic图像 --------------------
semantic_on_render = np.zeros((H, W), dtype=np.uint32)
semantic_on_render[v, u] = semantic_proj

# 显示
semantic_vis = (semantic_on_render % 256).astype(np.uint8)  # 简单伪彩色可视化
color_map = cv2.applyColorMap(semantic_vis * 10, cv2.COLORMAP_JET)

cv2.imshow("Projected Semantic onto Render", color_map)
cv2.imshow("Render RGB", rgb_render)

# 将语义图伪彩色转换成和RGB一样3通道
semantic_color = cv2.applyColorMap((semantic_on_render % 256).astype(np.uint8) * 10, cv2.COLORMAP_JET)

# 融合叠加（50%透明度）
blended = cv2.addWeighted(rgb_render, 0.7, semantic_color, 0.3, 0)

cv2.imshow("Render RGB + Semantic Overlay", blended)
cv2.waitKey(0)

