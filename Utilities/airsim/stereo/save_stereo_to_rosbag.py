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

# --------------------------------------------------
#               PATH CONFIGURATION
# --------------------------------------------------
# Replace these with your actual paths
left_image_dir  = "/home/yuan/airsim/data/rgb_left"   # Left camera images
right_image_dir = "/home/yuan/airsim/data/rgb_right"  # Right camera images
rosbag_path     = "/home/yuan/airsim/rosbags/stereo/orb_slam3_ros1.bag"  # Output ROS bag

# Ground truth file paths
old_gt_path = "/home/yuan/airsim/data/groundtruth.txt"
new_gt_path = os.path.join(os.path.dirname(rosbag_path), "groundtruth_new.txt")

# --------------------------------------------------
#          LOAD GROUND TRUTH (TUM FORMAT)
# --------------------------------------------------
with open(old_gt_path, 'r') as f:
    lines = f.readlines()

old_gt_data = []
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    # Expecting format: [timestamp, tx, ty, tz, qx, qy, qz, qw]
    old_gt_data.append(parts)

# Prepare the new ground truth file
new_gt_file = open(new_gt_path, 'w')
new_gt_file.write("# timestamp tx ty tz qx qy qz qw\n")  # TUM format header

# --------------------------------------------------
#            GET LEFT & RIGHT IMAGE LISTS
# --------------------------------------------------
left_files  = sorted([f for f in os.listdir(left_image_dir) if f.endswith(".png")])
right_files = sorted([f for f in os.listdir(right_image_dir) if f.endswith(".png")])

# Make sure there is a matching count of left & right images
if len(left_files) != len(right_files):
    rospy.logerr("Mismatch in number of left vs. right images!")
    exit(1)

# Check ground truth size vs. image count
if len(old_gt_data) < len(left_files):
    rospy.logwarn("Ground truth has fewer lines than images. Some frames will not have GT.")
elif len(old_gt_data) > len(left_files):
    rospy.logwarn("Ground truth has more lines than images. Some GT lines will not be used.")

# --------------------------------------------------
#             OPEN ROS BAG FOR WRITING
# --------------------------------------------------
bag = rosbag.Bag(rosbag_path, 'w')
bridge = CvBridge()

# --------------------------------------------------
#             SET FPS AND START TIME
# --------------------------------------------------
fps = 20
interval = 1.0 / fps
start_time = rospy.Time.now()

# --------------------------------------------------
#                MAIN PROCESSING
# --------------------------------------------------
try:
    rospy.loginfo(f"Saving {len(left_files)} pairs of left & right images to {rosbag_path} at {fps} FPS...")

    for i, (left_file, right_file) in enumerate(zip(left_files, right_files)):
        ros_time = start_time + rospy.Duration(i * interval)

        # --------------------------------------------------
        #           READ LEFT & RIGHT IMAGES
        # --------------------------------------------------
        # Left image
        left_path = os.path.join(left_image_dir, left_file)
        cv_left = cv2.imread(left_path)  # BGR in OpenCV

        # Right image
        right_path = os.path.join(right_image_dir, right_file)
        cv_right = cv2.imread(right_path)  # BGR in OpenCV

        # --------------------------------------------------
        #         CONVERT TO ROS IMAGE MESSAGES
        # --------------------------------------------------
        ros_left = bridge.cv2_to_imgmsg(cv_left, encoding="bgr8")
        ros_right = bridge.cv2_to_imgmsg(cv_right, encoding="bgr8")

        # Set timestamps
        ros_left.header.stamp  = ros_time
        ros_right.header.stamp = ros_time

        # --------------------------------------------------
        #          WRITE LEFT & RIGHT TO ROSBAG
        # --------------------------------------------------
        bag.write("/camera/left/image_raw", ros_left, ros_time)
        bag.write("/camera/right/image_raw", ros_right, ros_time)

        # --------------------------------------------------
        #         UPDATE GROUND TRUTH FILE
        # --------------------------------------------------
        if i < len(old_gt_data):
            # The old line: [timestamp, tx, ty, tz, qx, qy, qz, qw]
            _, tx, ty, tz, qx, qy, qz, qw = old_gt_data[i]
            new_timestamp = ros_time.to_sec()
            new_gt_file.write(f"{new_timestamp:.9f} {tx} {ty} {tz} {qx} {qy} {qz} {qw}\n")

        # (Optional) Logging every 1 second or so
        if (i + 1) % fps == 0:
            rospy.loginfo(f"Saved frame {i + 1}/{len(left_files)} to rosbag")

        rospy.sleep(interval)

finally:
    bag.close()
    new_gt_file.close()
    rospy.loginfo(f"Rosbag saved: {rosbag_path}")
    rospy.loginfo(f"New ground truth saved: {new_gt_path}")
