import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np

class AirSimRGBViewer(Node):
    def __init__(self):
        super().__init__('airsim_rgb_viewer')
        self.subscription = self.create_subscription(
            Image,
            '/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/scene_camera/image',
            # '/airsim_node/Drone1/front_center1/scene_camera/image',
            self.image_callback,
            10
        )
        self.bridge = CvBridge()
        self.get_logger().info("Subscribed to AirSim RGB image topic.")

    def image_callback(self, msg):
        try:
            # Convert the ROS2 Image message to OpenCV image
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"Failed to convert image: {e}")
            return

        # Show the image
        cv2.imshow("AirSim RGB Camera View", cv_image)
        cv2.waitKey(1)  # This is required to update the OpenCV window

class AirSimDepthViewer(Node):
    def __init__(self):
        super().__init__('airsim_depth_viewer')
        self.subscription = self.create_subscription(
            Image,
            '/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/depth_planar_camera/image',
            # '/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/depth_planar_camera/point_cloud',
            self.image_callback,
            10
        )
        self.bridge = CvBridge()
        self.get_logger().info("Subscribed to AirSim Depth image topic.")

    def image_callback(self, msg):
        try:
            # Convert to float32 depth image (in meters)
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='32FC1')

            # Clip to expected depth range for visualization
            min_depth = 0.5
            max_depth = 50.0
            depth_clipped = np.clip(cv_image, min_depth, max_depth)

            # Normalize to 0–255 for grayscale
            depth_normalized = ((depth_clipped - min_depth) / (max_depth - min_depth) * 255).astype(np.uint8)

            # Show as grayscale
            cv2.imshow("AirSim Depth Camera View", depth_normalized)
            cv2.waitKey(1)
        except Exception as e:
            self.get_logger().error(f"Failed to convert depth image: {e}")

class AirSimSemanticViewer(Node):
    def __init__(self):
        super().__init__('airsim_semantic_viewer')
        self.subscription = self.create_subscription(
            Image,
            '/viaduct/Sim/SceneDroneSensors/robots/Drone1/sensors/front_center1/segmentation_camera/image',
            self.image_callback,
            10
        )
        self.bridge = CvBridge()
        self.get_logger().info("Subscribed to AirSim Semantic image topic.")

    def image_callback(self, msg):
        try:
            # Semantic images are usually single-channel with label IDs per pixel (uint8)
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='mono8')
            # Apply color map for better visualization
            color_mapped = cv2.applyColorMap(cv_image, cv2.COLORMAP_HSV)
        except Exception as e:
            self.get_logger().error(f"Failed to convert semantic image: {e}")
            return

        cv2.imshow("AirSim Semantic Camera View", color_mapped)
        cv2.waitKey(1)


def RGB_viewer(args=None):
    rclpy.init(args=args)
    viewer = AirSimRGBViewer()
    try:
        rclpy.spin(viewer)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()
def Depth_viewer(args=None):
    rclpy.init(args=args)
    viewer = AirSimDepthViewer()
    try:
        rclpy.spin(viewer)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()
def Semantic_viewer(args=None):
    rclpy.init(args=args)
    viewer = AirSimSemanticViewer()
    try:
        rclpy.spin(viewer)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    mode = 'rgb' # [rgb, depth, semantic]
    if mode == 'rgb':
        RGB_viewer()
    elif mode == 'depth':
        Depth_viewer()
    elif mode == 'semantic':
        Semantic_viewer()
    else:
        print('Unknown mode')
