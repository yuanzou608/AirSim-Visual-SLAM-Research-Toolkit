import time

import numpy as np
import cv2
import matplotlib.pyplot as plt
import os
from pathlib import Path

def show_image(image, title="rgb"):
    if title == "depth":
        image_norm = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
        image_norm = image_norm.astype(np.uint8)
        cv2.imshow("depth", image_norm)
    elif title == "semantic":
        image_float = image.astype(np.float32)
        image_norm = cv2.normalize(image_float, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        color_map = cv2.applyColorMap(image_norm, cv2.COLORMAP_JET)
        cv2.imshow("semantic", color_map)
    else:
        cv2.imshow("rgb", image)

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

def read_images(render_file, depth_file, semantic_file):
    '''read images from raw data
    Args:
        render_file: rgb file, get from photo slam
        depth_file: raw depth file, get from airsim
        semantic_file: raw semantic file, get from airsim
    Returns:
        rgb, depth, semantic: post processed images'''

    # ------------------- 读取数据 --------------------
    # 读取深度 (单位: 米)
    depth = cv2.imread(str(depth_file), cv2.IMREAD_UNCHANGED).astype(np.float32) / 1000

    # 读取 AirSim 彩色语义图，并解码为真实 label ID
    semantic_rgb = cv2.imread(str(semantic_file), cv2.IMREAD_UNCHANGED)
    semantic_rgb = cv2.cvtColor(semantic_rgb, cv2.COLOR_BGR2RGB)
    semantic_label = semantic_rgb[:, :, 0] + semantic_rgb[:, :, 1] * 256 + semantic_rgb[:, :, 2] * 256 * 256
    semantic_label = semantic_label.astype(np.uint32)

    # 读取 render RGB
    rgb_render = cv2.imread(str(render_file))

    return depth, semantic_label, rgb_render

def back_projection(depth, semantic_label, rgb_render, intrinsic, pose):
    '''back projection from 2D to rendered
    Args:
        depth: depth image from airsom
        semantic_label: semantic label from airsim
        rgb_render: rgb image from photo slam
        intrinsic: camera intrinsic
        pose: current camera pose
    Returns:
        Xr_valid: x coordinate of 3D point cloud
        Yr_valid: y coordinate of 3D point cloud
        Zr_valid: z coordinate of 3D point cloud
        labels_valid: semantic label of 3D point cloud'''
    H, W = depth.shape # height, width of image
    fx = intrinsic[0, 0]
    fy = intrinsic[1, 1]
    cx = intrinsic[0, 2]
    cy = intrinsic[1, 2]

    i, j = np.meshgrid(np.arange(W), np.arange(H))
    # normalise , in order to get 3D position under camera coordination
    x = (i - cx) / fx
    y = (j - cy) / fy
    z = depth

    # get X, Y, Z in camera coordination
    X = x * z
    Y = y * z
    Z = z

    # point cloud corresponding each pixel
    # 第一步， 把 semantic image 反投影出来得到, Semantic Camera Space 下的三维点 points_cam
    points_cam = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    # semantic labe for each pixels, 376 * 672
    labels = semantic_label.reshape(-1)
    points_cam_hom = np.hstack([points_cam, np.ones((points_cam.shape[0], 1))]) # homography
    # 第二步, 把这些 3D 点从 semantic camera 坐标系 变换到 世界坐标系, points_world=pose_semantic^−1 * points_cam
    # 这里 pose 实际上应该是 pose_semantic, 但因为semantic 和 photo slam render的相机用的同一个(left camera)，所以都是pose
    points_world = (np.linalg.inv(pose) @ points_cam_hom.T).T # semantic camera -> world
    # 第三步, 把世界坐标系下的点，变换到 render camera 坐标系, points_render_cam=pose_render*points_world
    points_render_cam = (pose @ points_world.T).T[:, :3] # world -> rgb camera

    # ------------------- 投影到render RGB图像 --------------------
    Xr, Yr, Zr = points_render_cam[:, 0], points_render_cam[:, 1], points_render_cam[:, 2]

    # extract valid points, depth > 0
    valid_z = Zr > 0
    Xr_valid = Xr[valid_z]
    Yr_valid = Yr[valid_z]
    Zr_valid = Zr[valid_z]
    labels_valid = labels[valid_z] # semantic label

    return Xr_valid, Yr_valid, Zr_valid, labels_valid

def project(Xr_valid, Yr_valid, Zr_valid, labels_valid, depth, rgb_render, ts, output_dir):
    '''project 3D point colud to 2D plane
    Args:
        Xr_valid: x coordinate of 3D point cloud
        Yr_valid: y coordinate of 3D point cloud
        Zr_valid: z coordinate of 3D point cloud
        labels_valid: semantic label of 3D point cloud
        depth: depth file, get from airsim'''
    H, W = depth.shape
    # convert from 3D point cloud to 2D plane
    u = (fx * Xr_valid / Zr_valid + cx).astype(np.int32)
    v = (fy * Yr_valid / Zr_valid + cy).astype(np.int32)
    # only accept valid pixels
    valid_uv = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u, v, semantic_proj = u[valid_uv], v[valid_uv], labels_valid[valid_uv]

    # ------------------- 生成最终投影semantic图像 --------------------
    semantic_on_render = np.zeros((H, W), dtype=np.uint32)
    semantic_on_render[v, u] = semantic_proj

    semantic_vis = (semantic_on_render % 256).astype(np.uint8)  # 简单伪彩色可视化
    color_map = cv2.applyColorMap(semantic_vis * 10, cv2.COLORMAP_JET)

    # cv2.imshow("Projected Semantic onto Render", color_map)
    # cv2.imshow("Render RGB", rgb_render)

    # 将语义图伪彩色转换成和RGB一样3通道
    semantic_color = cv2.applyColorMap((semantic_on_render % 256).astype(np.uint8) * 10, cv2.COLORMAP_JET)

    # 融合叠加（50%透明度）
    # resize make rgb and semantic the same resolution
    semantic_color_resized = cv2.resize(semantic_color, (rgb_render.shape[1], rgb_render.shape[0]),
                                        interpolation=cv2.INTER_NEAREST)
    blended = cv2.addWeighted(rgb_render, 0.8, semantic_color_resized, 0.2, 0)

    blended_filename = output_dir / f"{ts}.png"
    cv2.imwrite(str(blended_filename), blended)
    cv2.imshow("Render RGB + Semantic Overlay", blended)
    cv2.waitKey(30)


if __name__ == '__main__':
    # ------------------- 配置文件 --------------------
    depth_dir = Path("/home/yuan/airsim/data/depth")
    semantic_dir = Path("/home/yuan/airsim/data/semantic")
    render_dir = Path("/home/yuan/airsim/data/photo_slam_frames")
    trajectory_file = Path("/home/yuan/airsim/data/CameraTrajectory_TUM.txt")
    output_dir = Path("/home/yuan/airsim/data/blended_frames")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 相机内参
    fx, fy, cx, cy = 336.0, 336.0, 336.0, 188.0
    intrinsic = np.array([[fx, 0, cx],
                          [0, fy, cy],
                          [0, 0, 1]])

    poses = load_poses(trajectory_file) # load all poses, 4*4

    count = 0
    # main loop
    for ts, pose in poses.items():
        render_file = render_dir / f"{ts}.png"
        depth_file = depth_dir / f"{ts}.png"
        semantic_file = semantic_dir / f"{ts}.png"
        # ensure file exists
        if (not render_file.exists()) or (not depth_file.exists()) or (not semantic_file.exists()):
            continue

        # read current depth, semantic, rendered
        depth, semantic_label, rgb_render = read_images(render_file, depth_file, semantic_file)

        # get valid point cloud and its semantic label
        Xr_valid, Yr_valid, Zr_valid, labels_valid = back_projection(depth, semantic_label, rgb_render, intrinsic, pose)

        project(Xr_valid, Yr_valid, Zr_valid, labels_valid, depth, rgb_render, ts, output_dir)




