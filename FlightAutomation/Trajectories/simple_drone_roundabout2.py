

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import time
from typing import List, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from adk_node.msg import WaypointPath


def chaikin_smooth(points: List[Tuple[float, float]], iters: int = 2, weight: float = 0.25) -> List[Tuple[float, float]]:
    if len(points) < 3 or iters <= 0:
        return points[:]

    result = points[:]
    for _ in range(iters):
        new_pts: List[Tuple[float, float]] = [result[0]]
        for i in range(len(result) - 1):
            p = result[i]
            q = result[i + 1]
            # Q = (1-w)P + wQ, R = wP + (1-w)Q
            Qx = (1.0 - weight) * p[0] + weight * q[0]
            Qy = (1.0 - weight) * p[1] + weight * q[1]
            Rx = weight * p[0] + (1.0 - weight) * q[0]
            Ry = weight * p[1] + (1.0 - weight) * q[1]
            new_pts.append((Qx, Qy))
            new_pts.append((Rx, Ry))
        new_pts.append(result[-1])
        result = new_pts
    return result


def densify_polyline(points: List[Tuple[float, float]], spacing: float = 1.0) -> List[Tuple[float, float]]:
    if spacing <= 0.0 or len(points) < 2:
        return points[:]

    out: List[Tuple[float, float]] = [points[0]]
    carry = 0.0
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        dx = x1 - x0
        dy = y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len == 0:
            continue

        nx = dx / seg_len
        ny = dy / seg_len

        dist = carry
        while dist + spacing <= seg_len:
            dist += spacing
            px = x0 + nx * dist
            py = y0 + ny * dist
            out.append((px, py))

        # leftover for next segment
        carry = (dist + spacing) - seg_len if (dist + spacing) > seg_len else 0.0

        # always append exact vertex
        out.append((x1, y1))

    return out


class SimpleDroneController(Node):
    def __init__(self):
        super().__init__('simple_drone_controller')

        # —— 基本配置 —— #
        self.drone_name = "Drone1"
        self.velocity = 8.0             # 水平速度 (m/s)：较平缓
        self.lookahead = 4.0            # 较大前瞻：让转向更圆滑
        self.adaptive_lookahead = 0.0   # 保持固定前瞻；如需自适应可设 >0
        self.publish_delay = 1.0        # 启动后延迟发布（秒）
        self.timeout_sec = 100000.0
        self._published = False
        self._have_z = False
        self._z_ned = 0.0
        self.last_print_time = 0.0

        # —— 原始目标点（不必严格经过，仅用于生成光滑路径） —— #
        self.anchor_xy: List[Tuple[float, float]] = [
            (0.0, 0.0),
            (45.0, -45.0),
            (60.0, -25.0),
            (45.0, 0.0),
            (0.0, -45.0),
            (-15.0, 0.0),
            (0.0, 15.0),
            (45, 0),
            (0, 0)
        ]

        # —— 平滑与采样参数 —— #
        self.smooth_iters = 2          # Chaikin 迭代次数（越大越圆滑）
        self.chaikin_weight = 0.25     # 角切比例（经典 0.25/0.75）
        self.target_spacing = 1.0      # 路径点间距（米），越小越密集更平滑

        # —— QoS，与原工程一致 —— #
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

        # 订阅无人机 odometry（用于读取当前高度 & 打印位置/高度）
        self.create_subscription(
            Odometry,
            f'/airsim_node/{self.drone_name}/odom_local_ned',
            self.odom_callback,
            10
        )

        # 定时器：延迟后尝试发布（只发一次；若尚未拿到 z，会在下个周期再尝试）
        self.create_timer(self.publish_delay, self._publish_once)

    # —— 里程计回调：记录首次 z（保持固定高度）并打印位姿 —— #
    def odom_callback(self, msg: Odometry):
        if not self._have_z:
            self._z_ned = float(msg.pose.pose.position.z)  # NED：z<0 表示高于地面
            self._have_z = True
            self.get_logger().info(
                f"Lock altitude: use current NED z={self._z_ned:.2f} (alt {-self._z_ned:.2f} m)"
            )

        now = time.time()
        if now - self.last_print_time >= 1.0:
            p = msg.pose.pose.position
            self.get_logger().info(
                f"Drone position: x={p.x:.2f}, y={p.y:.2f}, z={p.z:.2f} (alt {-p.z:.2f} m)"
            )
            self.last_print_time = now

    # —— 只发布一次；若还没拿到 z，则跳过等待下一次 —— #
    def _publish_once(self):
        if self._published:
            return
        if not self._have_z:
            self.get_logger().warn("Waiting for odom to lock altitude...")
            return

        # 1) 角切平滑（不过点，避免急拐弯）
        smoothed = chaikin_smooth(self.anchor_xy, iters=self.smooth_iters, weight=self.chaikin_weight)

        # 2) 均匀加密（控制每步距离，便于控制器跟踪并减少抖动）
        path_xy = densify_polyline(smoothed, spacing=self.target_spacing)

        # 3) 组装消息：统一使用锁定的 z
        wp = WaypointPath()
        wp.velocity = float(self.velocity)
        wp.wait_on_last_task = True
        wp.lookahead = float(self.lookahead)
        wp.adaptive_lookahead = float(self.adaptive_lookahead)
        wp.drive_train_type = 1
        wp.timeout_sec = float(self.timeout_sec)

        for (x, y) in path_xy:
            pose = PoseStamped()
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            pose.pose.position.z = float(self._z_ned)
            wp.path.append(pose)

        # 发布一次 + 轻微重发一次提升可靠性（与示例风格一致）
        self.wp_pub.publish(wp)
        self.get_logger().info(
            f"Published SMOOTH path: {len(wp.path)} pts, v={self.velocity} m/s, lookahead={self.lookahead}, spacing={self.target_spacing} m"
        )
        time.sleep(0.2)
        self.wp_pub.publish(wp)
        self.get_logger().info("Republished waypoints once for reliability.")

        self._published = True


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
