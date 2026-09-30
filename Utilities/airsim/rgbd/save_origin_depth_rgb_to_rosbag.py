#!/usr/bin/env python3
import rospy
import rosbag
import os
import numpy as np
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image


# Initialize ROS node
rospy.init_node("image_saver")

# Paths
image_dir = "/home/yuan/dataset/my_data/RGBD13fps/rgb"  # RGB images directory
depth_dir = "/home/yuan/dataset/my_data/RGBD13fps/depth"  # Depth images directory (now .npy)
rosbag_path = "/home/yuan/dataset/my_data/RGBD13fps/rosbag/RGBD13fps.bag"  # ROS bag file path

# FPS settings
fps = 13
interval = 1.0 / fps

# Ground truth file
old_gt_path = "/home/yuan/dataset/my_data/RGBD13fps/groundtruth.txt"
new_gt_path = os.path.join(os.path.dirname(rosbag_path), "groundtruth.txt")

# Read old ground truth (TUM format)
with open(old_gt_path, 'r') as f:
    lines = f.readlines()

old_gt_data = []
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    old_gt_data.append(parts)  # [timestamp, tx, ty, tz, qx, qy, qz, qw]

# Create new ground truth file
new_gt_file = open(new_gt_path, 'w')
new_gt_file.write("# timestamp tx ty tz qx qy qz qw\n")  # TUM format header

# Get list of files
rgb_files = sorted([f for f in os.listdir(image_dir) if f.endswith(".png")])
depth_files = sorted([f for f in os.listdir(depth_dir) if f.endswith((".npy", ".png"))])

# Auto detect depth format
depth_ext = os.path.splitext(depth_files[0])[1].lower()
use_npy = (depth_ext == ".npy")
rospy.loginfo(f"Depth files detected as {'NumPy (.npy)' if use_npy else 'PNG (.png)'} format.")


# Ensure equal number of frames
if len(rgb_files) != len(depth_files):
    rospy.logerr("Mismatch in RGB and Depth frames! Ensure they have the same number of images.")
    exit()

if len(old_gt_data) < len(rgb_files):
    rospy.logwarn("Ground truth has fewer lines than images. Some frames won't have GT!")
elif len(old_gt_data) > len(rgb_files):
    rospy.logwarn("Ground truth has more lines than images. Some GT lines won't be used!")

# Open ROS bag
bag = rosbag.Bag(rosbag_path, 'w')

# CV Bridge for OpenCV <-> ROS conversions
bridge = CvBridge()



try:
    rospy.loginfo(f"Saving {len(rgb_files)} RGB & Depth images to {rosbag_path} at {fps} FPS...")
    start_time = rospy.Time.now()

    for i, (rgb_file, depth_file) in enumerate(zip(rgb_files, depth_files)):
        ros_time = start_time + rospy.Duration(i * interval)

        # Read RGB Image
        rgb_path = os.path.join(image_dir, rgb_file)
        cv_rgb = cv2.imread(rgb_path)
        
        # read depth image
        depth_path = os.path.join(depth_dir, depth_file)
        if use_npy:
            cv_depth = np.load(depth_path).astype(np.float32) / 1000 # in mm
        else:
            cv_depth = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED).astype(np.float32) # in mm


        # Convert images to ROS format
        ros_rgb = bridge.cv2_to_imgmsg(cv_rgb, encoding="bgr8")
        ros_depth = bridge.cv2_to_imgmsg(cv_depth, encoding="32FC1")

        # Assign timestamps
        ros_rgb.header.stamp = ros_time
        ros_depth.header.stamp = ros_time

        # Write to ROS bag
        bag.write("/camera/rgb/image_raw", ros_rgb, ros_time)
        bag.write("/camera/depth_registered/image_raw", ros_depth, ros_time)

        # Update ground truth with new timestamp
        if i < len(old_gt_data):
            _, tx, ty, tz, qx, qy, qz, qw = old_gt_data[i]
            new_timestamp = ros_time.to_sec()
            new_gt_file.write(f"{new_timestamp:.9f} {tx} {ty} {tz} {qx} {qy} {qz} {qw}\n")

        if (i + 1) % fps == 0:
            rospy.loginfo(f"Saved frame {i + 1}/{len(rgb_files)} to rosbag")

        rospy.sleep(interval)

finally:
    bag.close()
    new_gt_file.close()
    rospy.loginfo(f"Rosbag saved: {rosbag_path}")
    rospy.loginfo(f"New ground truth saved: {new_gt_path}")
