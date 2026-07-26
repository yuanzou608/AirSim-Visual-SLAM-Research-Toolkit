#!/usr/bin/env python3
import airsim
import rospy
import rosbag
import os
import numpy as np
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()

# Initialize ROS node and publishers
rospy.init_node('airsim_stereo_publisher')
pub_rgb_left = rospy.Publisher('/camera/left/image_raw', Image, queue_size=10)
pub_rgb_right = rospy.Publisher('/camera/right/image_raw', Image, queue_size=10)

# CV Bridge for OpenCV <-> ROS conversions
bridge = CvBridge()

save_dir = "/home/yuan/airsim/rosbags/stereo"
# -- Ground truth file (TUM format) ------------------------------------
# We’ll store: timestamp tx ty tz qx qy qz qw
tum_file_path = os.path.join(save_dir, "groundtruth_new.txt")  # <-- ADDED
tum_file = open(tum_file_path, "w")  # <-- ADDED
tum_file.write("# timestamp tx ty tz qx qy qz qw\n")  # <-- ADDED
# -------------------------------------------------------------------

while not rospy.is_shutdown():
    # Capture RGB and Depth images
    responses = client.simGetImages([
        airsim.ImageRequest("front_left_custom", airsim.ImageType.Scene, False, False),
        airsim.ImageRequest("front_right_custom", airsim.ImageType.Scene, False, False),
        airsim.ImageRequest("front_left_custom", airsim.ImageType.DepthPlanar, True)
    ])

    # validate the length of responses
    if len(responses) != 3:
        print(f"Warn: Skipping frame, Incomplete image responses received")
        continue

    rgb_left_response = responses[0]
    rgb_right_response = responses[1]
    depth_left_response = responses[2]

    # process rgb images
    rgb_left_img1d = np.frombuffer(rgb_left_response.image_data_uint8, dtype=np.uint8)
    rgb_left_img = rgb_left_img1d.reshape(rgb_left_response.height, rgb_left_response.width, 3)

    rgb_right_img1d = np.frombuffer(rgb_right_response.image_data_uint8, dtype=np.uint8)
    rgb_right_img = rgb_right_img1d.reshape(rgb_right_response.height, rgb_right_response.width, 3)

    # Process Depth Image (Raw 32-bit float)
    depth_left_img1d = np.array(depth_left_response.image_data_float, dtype=np.float32)
    depth_left_img = depth_left_img1d.reshape(depth_left_response.height, depth_left_response.width)

    # Convert images to ROS format
    ros_rgb_left = bridge.cv2_to_imgmsg(rgb_left_img, encoding="bgr8")
    ros_rgb_right = bridge.cv2_to_imgmsg(rgb_right_img, encoding="bgr8")

    # Add timestamps
    stamp = rospy.Time.now()
    ros_rgb_left.header.stamp = stamp
    ros_rgb_right.header.stamp = stamp

    # Publish
    pub_rgb_left.publish(ros_rgb_left)
    pub_rgb_right.publish(ros_rgb_right)

    # --- Get and record ground-truth pose in TUM format ------------------
    kinematics = client.simGetGroundTruthKinematics()  # <-- ADDED
    pos = kinematics.position  # <-- ADDED
    orn = kinematics.orientation  # <-- ADDED
    # Write out: timestamp x y z qx qy qz qw
    tum_file.write(f"{stamp.to_sec():6f} {pos.x_val} {pos.y_val} {pos.z_val} "
                   f"{orn.x_val} {orn.y_val} {orn.z_val} {orn.w_val}\n")  # <-- ADDED
    # ---------------------------------------------------------------------



