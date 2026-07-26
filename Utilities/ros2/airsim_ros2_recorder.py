#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Point, Quaternion

import airsim
import cv2
import numpy as np

# For converting between OpenCV images and ROS2 sensor_msgs/Image
# In ROS2, cv_bridge is typically 'apt install ros-$DISTRO-cv-bridge'
from cv_bridge import CvBridge


class AirSimRecorderNode(Node):
    def __init__(self):
        super().__init__('airsim_recorder_node')
        self.get_logger().info("Starting AirSim Recorder Node...")

        # Connect to AirSim
        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        self.get_logger().info("Connected to AirSim.")

        # Initialize ROS publishers
        self.image_pub = self.create_publisher(Image, '/airsim/camera', 10)
        self.odom_pub = self.create_publisher(Odometry, '/airsim/odom', 10)

        # For converting OpenCV images to ROS Image
        self.bridge = CvBridge()

        # Start in paused mode
        self.client.simPause(True)

        # Desired "virtual" frame rate (Hz)
        self.frame_rate = 30.0
        self.time_step = 1.0 / self.frame_rate
        self.sim_time = 0.0

        # Example: number of frames to record
        self.max_frames = 300
        self.current_frame = 0

        # We can use a timer to step the simulation, or simply call a function repeatedly
        # We'll do it in a timer for demonstration (though it's not real-time).
        self.timer_period = 0.1  # Real seconds between "stepping" events
        self.timer = self.create_timer(self.timer_period, self.record_step)

        self.get_logger().info("Recorder Node setup complete.")

    def record_step(self):
        """This method is called periodically in real time, but inside it we:
           1) Step the AirSim simulation by self.time_step
           2) Capture data
           3) Publish to ROS2
           4) Increment self.sim_time
        """
        if self.current_frame >= self.max_frames:
            self.get_logger().info(f"Captured {self.max_frames} frames. Stopping timer.")
            self.destroy_timer(self.timer)
            # Optionally unpause sim or do something else
            self.client.simPause(False)
            return

        # 1. Step simulation by time_step
        self.client.simContinueForTime(self.time_step)
        self.client.simPause(True)
        self.sim_time += self.time_step

        # 2. Capture images
        raw_image = self.client.simGetImage("0", airsim.ImageType.Scene)
        if raw_image is not None:
            # Convert raw bytes to np array
            np_arr = np.frombuffer(raw_image, dtype=np.uint8)
            img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            # Convert to ROS2 Image message
            ros_image = self.bridge.cv2_to_imgmsg(img_bgr, encoding='bgr8')

            # For the header stamp, we use the "simulated" time
            # There's not a default simulated clock in ROS2 here,
            # but we can embed this time in the header as a best-effort approach.
            # (Alternatively, you could publish your own Clock / Time reference.)
            sec = int(self.sim_time)
            nanosec = int((self.sim_time - sec) * 1e9)
            ros_image.header.stamp.sec = sec
            ros_image.header.stamp.nanosec = nanosec

            self.image_pub.publish(ros_image)

        # 3. Capture odometry (ground truth kinematics)
        kin = self.client.simGetGroundTruthKinematics()
        odom_msg = Odometry()
        odom_msg.header.frame_id = 'world'
        odom_msg.header.stamp.sec = int(self.sim_time)
        odom_msg.header.stamp.nanosec = int((self.sim_time - int(self.sim_time)) * 1e9)

        # Position
        odom_msg.pose.pose.position.x = kin.position.x_val
        odom_msg.pose.pose.position.y = kin.position.y_val
        odom_msg.pose.pose.position.z = kin.position.z_val

        # Orientation
        # AirSim returns quaternion as w, x, y, z (in kin.orientation),
        # while ROS often uses x, y, z, w. So we reorder carefully.
        odom_msg.pose.pose.orientation = Quaternion(
            x=kin.orientation.x_val,
            y=kin.orientation.y_val,
            z=kin.orientation.z_val,
            w=kin.orientation.w_val
        )

        # Linear velocity
        odom_msg.twist.twist.linear.x = kin.linear_velocity.x_val
        odom_msg.twist.twist.linear.y = kin.linear_velocity.y_val
        odom_msg.twist.twist.linear.z = kin.linear_velocity.z_val

        # Angular velocity
        odom_msg.twist.twist.angular.x = kin.angular_velocity.x_val
        odom_msg.twist.twist.angular.y = kin.angular_velocity.y_val
        odom_msg.twist.twist.angular.z = kin.angular_velocity.z_val

        self.odom_pub.publish(odom_msg)

        self.current_frame += 1
        self.get_logger().info(f"Frame {self.current_frame}/{self.max_frames} recorded (sim_time={self.sim_time:.3f}s)")

def main(args=None):
    rclpy.init(args=args)
    node = AirSimRecorderNode()
    rclpy.spin(node)  # Spin to process callbacks
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
