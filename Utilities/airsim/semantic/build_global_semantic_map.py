import numpy as np
import cv2
import open3d as o3d
from scipy.spatial.transform import Rotation as R
from pathlib import Path
from tqdm import tqdm

# === 参数 ===
fx, fy = 336.0, 336.0
cx, cy = 336.0, 188.0
depth_dir = Path("/home/yuan/airsim/data/depth")
semantic_dir = Path("/home/yuan/airsim/data/semantic")
trajectory_path = Path("/home/yuan/airsim/data/CameraTrajectory_TUM.txt")

# === 加载 TUM 轨迹 ===
def load_poses(tum_file):
    poses = {}
    with open(tum_file, "r") as f:
        for line in f:
            if line.startswith("#"): continue
            parts = line.strip().split()
            ts = float(parts[0])
            t = np.array([float(p) for p in parts[1:4]])
            q = np.array([float(p) for p in parts[4:8]])  # [x, y, z, w]
            Rw = R.from_quat(q).as_matrix()
            Tcw = np.eye(4)
            Tcw[:3, :3] = Rw
            Tcw[:3, 3] = t
            poses[ts] = np.linalg.inv(Tcw)  # 相机→世界
    return poses

poses = load_poses(trajectory_path)
# === 全局点云容器 ===
all_points = []
all_colors = []
batch_size = 500
batch_id = 0

# === 遍历所有帧 ===
depth_files = sorted(depth_dir.glob("*.png"))
for i, depth_path in enumerate(tqdm(depth_files)):
    ts = float(depth_path.stem.split("/")[0])
    if ts not in poses:
        continue

    # 加载图像
    depth_img = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED).astype(np.float32)
    if depth_img.max() > 100:  # mm → m
        depth_img /= 1000.0

    semantic_path = semantic_dir / f"{ts:.6f}.png"
    if not semantic_path.exists():
        continue

    semantic_img = cv2.imread(str(semantic_path), cv2.IMREAD_COLOR)
    semantic_img = cv2.cvtColor(semantic_img, cv2.COLOR_BGR2RGB)

    H, W = depth_img.shape
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    z = depth_img
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy

    valid = (z > 0)
    xyz_cam = np.stack([x, y, z], axis=-1)[valid]
    colors = semantic_img[valid] / 255.0

    # 变换到世界坐标
    Twc = poses[ts]
    xyz_world = (Twc[:3, :3] @ xyz_cam.T + Twc[:3, 3:4]).T

    all_points.append(xyz_world)
    all_colors.append(colors)

    # ✅ 每 batch_size 帧保存一次
    if (i + 1) % batch_size == 0:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(np.vstack(all_points))
        pcd.colors = o3d.utility.Vector3dVector(np.vstack(all_colors))
        # ✅ 下采样：去冗余压缩体素
        pcd = pcd.voxel_down_sample(voxel_size=0.1)  # 体素大小单位是米
        o3d.io.write_point_cloud(f"semantic_map_batch_{batch_id:03d}.ply", pcd)
        print(f"✅ Saved batch {batch_id}")
        all_points.clear()
        all_colors.clear()
        batch_id += 1

# ✅ 保存最后一批
if all_points:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.vstack(all_points))
    pcd.colors = o3d.utility.Vector3dVector(np.vstack(all_colors))
    # ✅ 下采样：去冗余压缩体素
    pcd = pcd.voxel_down_sample(voxel_size=0.05)  # 体素大小单位是米
    o3d.io.write_point_cloud(f"semantic_map_batch_{batch_id:03d}.ply", pcd)
    print(f"✅ Saved final batch {batch_id}")


