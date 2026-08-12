#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROS2 recorder (synchronized) for RGB / Depth / Semantic / GT Pose, with TUM-style associations.

- Uses ApproximateTimeSynchronizer to get RGB+Depth+Semantic together
- Saves PNG under SAVE_DIR/{rgb,depth,semantic}
  * RGB & Semantic: saved as-is (passthrough) PNG
  * Depth (32FC1 meters): converted to uint16 millimeters PNG
- Writes lists: rgb.txt, depth.txt, semantic.txt
- Writes groundtruth.txt in TUM format: timestamp tx ty tz qx qy qz qw
- Writes associations_rgb_depth.txt as: t_rgb path_rgb t_depth path_depth (|Δt|<=ASSOC_THRESH)

Requirements: rclpy, cv_bridge, numpy, opencv-python, message_filters
"""

import os
import time
import numpy as np
import cv2

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from geometry_msgs.msg import PoseStamped
from cv_bridge import CvBridge

from message_filters import Subscriber, ApproximateTimeSynchronizer

# ================== USER CONFIG ==================

TOPIC_RGB     = "/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/scene_camera/image"
TOPIC_DEPTH   = "/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/depth_planar_camera/image"
TOPIC_SEM     = "/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/segmentation_camera/image"
TOPIC_GT_POSE = "/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/scene_camera/pose"

SAVE_DIR = "/home/yuan/data2tb/dataset/temp_data"   # 修改为你想保存的绝对路径
PRINT_EVERY_SEC = 1.0            # 状态打印间隔（秒）

# 同步器参数
SYNC_QUEUE_SIZE = 20
SYNC_SLOP_SEC   = 0.02           # 近似同步窗口（秒），可按需要调小/调大

# 关联阈值（仅当 |t_rgb - t_depth| <= ASSOC_THRESH 才写 associations）
ASSOC_THRESH = 0.01             # 秒

# =================================================


def ensure_dirs(root: str):
    os.makedirs(root, exist_ok=True)
    paths = {
        "rgb": os.path.join(root, "rgb"),
        "depth": os.path.join(root, "depth"),
        "semantic": os.path.join(root, "semantic"),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths


class SyncedImagePoseRecorder(Node):
    def __init__(self):
        super().__init__("synced_image_pose_recorder")

        self.paths = ensure_dirs(SAVE_DIR)
        self.bridge = CvBridge()
        self.last_print = 0.0

        # 文本日志
        self.rgb_txt   = open(os.path.join(SAVE_DIR, "rgb.txt"), "w")
        self.depth_txt = open(os.path.join(SAVE_DIR, "depth.txt"), "w")
        self.sem_txt   = open(os.path.join(SAVE_DIR, "semantic.txt"), "w")
        self.assoc_txt = open(os.path.join(SAVE_DIR, "associations_rgb_depth.txt"), "w")
        self.gt_txt    = open(os.path.join(SAVE_DIR, "groundtruth.txt"), "w")
        self.gt_txt.write("# timestamp tx ty tz qx qy qz qw\n")

        # 常见传感器 QoS（Best Effort / Volatile）
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # 同步订阅三个图像
        self.rgb_sub   = Subscriber(self, Image, TOPIC_RGB,   qos_profile=sensor_qos)
        self.depth_sub = Subscriber(self, Image, TOPIC_DEPTH, qos_profile=sensor_qos)
        self.sem_sub   = Subscriber(self, Image, TOPIC_SEM,   qos_profile=sensor_qos)

        self.ts = ApproximateTimeSynchronizer(
            [self.rgb_sub, self.depth_sub, self.sem_sub],
            SYNC_QUEUE_SIZE,
            SYNC_SLOP_SEC
        )
        self.ts.registerCallback(self.synced_cb)

        # 位姿独立订阅
        self.create_subscription(PoseStamped, TOPIC_GT_POSE, self.pose_cb, sensor_qos)

        self.get_logger().info("Synced recorder started.")
        self.get_logger().info(f"Saving to: {os.path.abspath(SAVE_DIR)}")
        self.get_logger().info(f"RGB:   {TOPIC_RGB}")
        self.get_logger().info(f"Depth: {TOPIC_DEPTH} (32FC1 -> uint16 mm PNG)")
        self.get_logger().info(f"Sem:   {TOPIC_SEM}")
        self.get_logger().info(f"Pose:  {TOPIC_GT_POSE}")
        self.get_logger().info(f"Sync:  queue={SYNC_QUEUE_SIZE}, slop={SYNC_SLOP_SEC*1000:.1f} ms")
        self.get_logger().info(f"Assoc: threshold={ASSOC_THRESH*1000:.1f} ms")

    # ---------- synced callback ----------
    def synced_cb(self, rgb_msg: Image, depth_msg: Image, sem_msg: Image):
        """
        同步后的三帧图像一起回调。分别使用各自的原始时间戳作为文件名(TUM 风格）。
        associations_rgb_depth.txt 记录 RGB 与 Depth 的时间戳对应（限于阈值内）。
        """
        try:
            # 提取各自原始时间戳
            ts_rgb   = self.stamp(rgb_msg)
            ts_depth = self.stamp(depth_msg)
            ts_sem   = self.stamp(sem_msg)

            # --- RGB 保存（passthrough）---
            rgb_img  = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding="passthrough")
            rgb_name = f"{ts_rgb:.6f}.png"
            rgb_rel  = f"rgb/{rgb_name}"
            cv2.imwrite(os.path.join(self.paths["rgb"], rgb_name), rgb_img)
            self.rgb_txt.write(f"{ts_rgb:.6f} {rgb_rel}\n")

            # --- Depth 保存（32FC1 m -> uint16 mm PNG）---
            depth_arr = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding="passthrough")
            depth_mm = (depth_arr * 1000.0).astype(np.float32)
            depth_mm = np.nan_to_num(depth_mm, nan=0.0, posinf=65535.0, neginf=0.0)
            depth_mm = np.clip(depth_mm, 0.0, 65535.0).astype(np.uint16)
            depth_name = f"{ts_depth:.6f}.png"
            depth_rel  = f"depth/{depth_name}"
            cv2.imwrite(os.path.join(self.paths["depth"], depth_name), depth_mm)
            self.depth_txt.write(f"{ts_depth:.6f} {depth_rel}\n")

            # --- Semantic 保存（passthrough）---
            sem_img  = self.bridge.imgmsg_to_cv2(sem_msg, desired_encoding="passthrough")
            sem_name = f"{ts_sem:.6f}.png"
            sem_rel  = f"semantic/{sem_name}"
            cv2.imwrite(os.path.join(self.paths["semantic"], sem_name), sem_img)
            self.sem_txt.write(f"{ts_sem:.6f} {sem_rel}\n")

            # --- Associations: 仅当时间差在阈值内才写一行 ---
            dt = abs(ts_rgb - ts_depth)
            if dt <= ASSOC_THRESH:
                self.assoc_txt.write(f"{ts_rgb:.6f} {rgb_rel} {ts_depth:.6f} {depth_rel}\n")

            self.maybe_print("synced_rgb_depth_sem", ts_rgb)

        except Exception as e:
            self.get_logger().warn(f"Synced save error: {e}")

    # ---------- pose callback ----------
    def pose_cb(self, msg: PoseStamped):
        ts = self.stamp(msg)
        p = msg.pose.position
        q = msg.pose.orientation
        # TUM: t tx ty tz qx qy qz qw
        self.gt_txt.write(
            f"{ts:.6f} {p.x:.6f} {p.y:.6f} {p.z:.6f} {q.x:.6f} {q.y:.6f} {q.z:.6f} {q.w:.6f}\n"
        )
        self.maybe_print("pose", ts)

    # ---------- helpers ----------
    @staticmethod
    def stamp(msg) -> float:
        h = getattr(msg, "header", None)
        s = getattr(h, "stamp", None) if h else None
        if s:
            return s.sec + s.nanosec * 1e-9
        return time.time()

    def maybe_print(self, tag: str, ts: float):
        now = time.time()
        if now - self.last_print >= PRINT_EVERY_SEC:
            self.get_logger().info(f"[{tag}] ts={ts:.6f} | saved")
            self.last_print = now

    def close_all(self):
        for f in [self.rgb_txt, self.depth_txt, self.sem_txt, self.assoc_txt, self.gt_txt]:
            try:
                if f:
                    f.flush()
                    f.close()
            except Exception:
                pass


def main():
    rclpy.init()
    node = SyncedImagePoseRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close_all()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
