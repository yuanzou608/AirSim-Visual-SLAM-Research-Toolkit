#!/usr/bin/env python3
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from adk_node.msg import WaypointPath


class SimpleDroneController(Node):
    def __init__(self):
        super().__init__('simple_drone_controller')

        self.drone_name = "Drone1"
        self.velocity = 4.0
        self.height = -30.0
        self.publish_delay = 1.0
        self.last_print_time = 0.0  # 上一次打印的时间戳

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # 发布 waypoints
        self.wp_pub = self.create_publisher(
            WaypointPath,
            f'/adk_node/input/{self.drone_name}/waypoints',
            qos
        )

        # 订阅无人机 odometry
        self.create_subscription(
            Odometry,
            f'/airsim_node/{self.drone_name}/odom_local_ned',
            self.odom_callback,
            10
        )

        # 延迟后发布路径
        self.create_timer(self.publish_delay, self._publish_once)

        self._published = False

    def _publish_once(self):
        if self._published:
            return

        path_points_xyz = [
            [0.0,  0.0,  self.height],
            # [318.0,  134.0,  self.height],
            # [300.0, 100.0,  self.height],
            # [180.0,  65.0,  self.height],
            # [0.0,  0.0,  self.height],
            # [20.0,  200.0,  self.height],
        ]

        wp = WaypointPath()
        wp.velocity = float(self.velocity)
        wp.wait_on_last_task = True
        wp.lookahead = -1.0
        wp.adaptive_lookahead = 0.0
        wp.drive_train_type = 1
        wp.timeout_sec = 100000.0

        for x, y, z in path_points_xyz:
            pose = PoseStamped()
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            pose.pose.position.z = float(z)
            wp.path.append(pose)

        self.wp_pub.publish(wp)
        self.get_logger().info(f"Published {len(wp.path)} waypoints at {self.velocity} m/s.")
        self._published = True

    def odom_callback(self, msg: Odometry):
        now = time.time()
        if now - self.last_print_time >= 1.0:  # 距离上次打印 >= 1 秒
            pos = msg.pose.pose.position
            altitude = -pos.z  # NED 坐标系，z 负数表示上方
            self.get_logger().info(
                f"Drone position: x={pos.x:.2f}, y={pos.y:.2f}, z={pos.z:.2f} (altitude {altitude:.2f} m)"
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
