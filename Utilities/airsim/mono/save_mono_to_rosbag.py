#!/usr/bin/env python3
import rospy
import rosbag
import os
import cv2
import numpy as np
from cv_bridge import CvBridge
from sensor_msgs.msg import Image

# Initialize ROS node
rospy.init_node("image_saver_mono")

# 0) Define file paths
image_dir = "/home/yuan/airsim/data/rgb_right"    # mono images directory
rosbag_path = "/home/yuan/airsim/rosbags/mono/orb_slam3_ros1.bag"  # Path to save the ROS bag

# -------------------------------------------------------------------
# 1) Open old ground truth file (TUM format) and read lines
#    We assume lines like:
#       # timestamp tx ty tz qx qy qz qw
#       1678130502.123456 0.1 0.2 0.3 0.0 0.0 0.0 1.0
# -------------------------------------------------------------------
old_gt_path = "/home/yuan/airsim/data/groundtruth.txt"  # adapt if needed
with open(old_gt_path, 'r') as f:
    lines = f.readlines()

# Parse ground truth lines into a list (ignore comment lines)
old_gt_data = []
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    # parts: [timestamp, tx, ty, tz, qx, qy, qz, qw]
    old_gt_data.append(parts)

# 2) Create a new ground truth file in the same folder as rosbag
new_gt_path = os.path.join(os.path.dirname(rosbag_path), "groundtruth_new.txt")
new_gt_file = open(new_gt_path, 'w')
new_gt_file.write("# timestamp tx ty tz qx qy qz qw\n")  # TUM header

# 3) Gather list of image files
image_files = sorted([f for f in os.listdir(image_dir) if f.endswith(".png")])
num_images = len(image_files)

# (Optional) safety check if ground truth lines match image frames
if len(old_gt_data) < num_images:
    rospy.logwarn("Ground truth file has fewer lines than images. Extra frames won't have GT!")
elif len(old_gt_data) > num_images:
    rospy.logwarn("Ground truth file has more lines than images. Some GT lines won't be used!")

# 4) Open ROS bag
bag = rosbag.Bag(rosbag_path, 'w')
bridge = CvBridge()

# 5) FPS and timing
fps = 20
interval = 1.0 / fps
start_time = rospy.Time.now()  # This will be our reference time zero

try:
    rospy.loginfo(f"Saving {num_images} mono images to {rosbag_path} at {fps} FPS...")

    for i, image_file in enumerate(image_files):
        # Generate a consistent timestamp based on an initial start_time plus i * interval
        ros_time = start_time + rospy.Duration(i * interval)

        # Read image
        image_path = os.path.join(image_dir, image_file)
        cv_image = cv2.imread(image_path)

        # Convert OpenCV to ROS Image
        ros_image = bridge.cv2_to_imgmsg(cv_image, encoding="bgr8")
        ros_image.header.stamp = ros_time

        # Write to bag
        bag.write("/camera/image_raw", ros_image, ros_time)

        # Write ground truth line (if available)
        if i < len(old_gt_data):
            # old_gt_data[i] = [old_ts, tx, ty, tz, qx, qy, qz, qw]
            _, tx, ty, tz, qx, qy, qz, qw = old_gt_data[i]
            new_timestamp = ros_time.to_sec()
            new_gt_file.write(f"{new_timestamp:.9f} {tx} {ty} {tz} {qx} {qy} {qz} {qw}\n")

        # Progress message
        if (i + 1) % fps == 0:
            rospy.loginfo(f"Saved frame {i + 1}/{num_images} to rosbag")

        # Sleep to maintain ~20 FPS (simulate real-time pacing)
        rospy.sleep(interval)

finally:
    bag.close()
    new_gt_file.close()
    rospy.loginfo(f"Rosbag saved: {rosbag_path}")
    rospy.loginfo(f"New ground truth saved: {new_gt_path}")
