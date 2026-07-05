#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from adk_node.msg import WaypointPath


def build_rect_path(x0, y0, width, height, z, step=2.0):
    """
    按顺时针生成矩形四边的密集航点,step 为相邻点间距（米）
    通过更密的点 + 小 lookahead,让无人机沿着矩形边走,而不是抄直线。
    """
    import numpy as np
    pts = []
    corners = [
        (x0, y0),                   # 左下
        (x0 + width, y0),           # 右下
        (x0 + width, y0 + height),  # 右上
        (x0, y0 + height),          # 左上
        (x0, y0),                   # 回到左下
    ]
    for (ax, ay), (bx, by) in zip(corners[:-1], corners[1:]):
        length = math.hypot(bx - ax, by - ay)
        n = max(2, int(length / step))  # 至少两个点
        # endpoint=False 避免重复角点，最后统一补回起点
        for t in np.linspace(0.0, 1.0, n, endpoint=False):
            x = ax + (bx - ax) * t
            y = ay + (by - ay) * t
            pts.append([x, y, z])
    pts.append([x0, y0, z])  # 最后补回起点
    return pts


class SimpleDroneController(Node):
    def __init__(self):
        super().__init__('simple_drone_controller')

        # —— 基本配置 —— #
        self.drone_name = "Drone1"
        self.velocity = 2.0      # 建议 3~6 m/s 起步
        self.height = -30.0      # NED 高度（负数向下）
        self.publish_delay = 1.0 # 启动后延迟发布（秒）
        self.last_print_time = 0.0  # 上次打印时间

        # —— QoS，与原工程一致，确保 ADK 能接到 —— #
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # 发布 WaypointPath（整条路径一次性发）
        self.wp_pub = self.create_publisher(
            WaypointPath,
            f'/adk_node/input/{self.drone_name}/waypoints',
            qos
        )

        # 订阅无人机 odometry（用于打印位置/高度）
        self.create_subscription(
            Odometry,
            f'/airsim_node/{self.drone_name}/odom_local_ned',
            self.odom_callback,
            10
        )

        # 延迟后发布路径（只发一次）
        self.create_timer(self.publish_delay, self._publish_once)
        self._published = False

    def _publish_once(self):
        if self._published:
            return

        # ===== 矩形参数（按你的地图坐标改） =====
        x0, y0 = 0.0, -60.0      # 左下角坐标
        width, height = 50.0, 50.0 # 矩形宽高（米）
        step = 2.0                 # 航点间距（米）：越小越贴边；越大越平滑

        # 生成密集矩形航点
        path_points_xyz = build_rect_path(x0, y0, width, height, self.height, step=step)

        # 组装 WaypointPath
        wp = WaypointPath()
        wp.velocity = float(self.velocity)
        wp.wait_on_last_task = True     # 只在最后一个点等待
        wp.lookahead = 2.0              # ★ 小前瞻，避免抄直线（可调 1.0~3.0）
        wp.adaptive_lookahead = 0.0     # 固定前瞻
        wp.drive_train_type = 1
        wp.timeout_sec = 100000.0

        for x, y, z in path_points_xyz:
            pose = PoseStamped()
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            pose.pose.position.z = float(z)
            wp.path.append(pose)

        # 发布一次（可选重发一次提高可靠性）
        self.wp_pub.publish(wp)
        self.get_logger().info(
            f"Published rectangle path: {len(wp.path)} points, v={self.velocity} m/s, lookahead=2.0"
        )
        time.sleep(0.2)
        self.wp_pub.publish(wp)
        self.get_logger().info("Republished waypoints once for reliability.")

        self._published = True

    def odom_callback(self, msg: Odometry):
        # 每秒打印一次位置和高度
        now = time.time()
        if now - self.last_print_time >= 1.0:
            p = msg.pose.pose.position
            altitude = -p.z  # NED：z 为负表示高于地面
            self.get_logger().info(
                f"Drone position: x={p.x:.2f}, y={p.y:.2f}, z={p.z:.2f} (altitude {altitude:.2f} m)"
            )
            self.last_print_time = now


def main():
    rclpy.init()
    node = SimpleDroneController()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
