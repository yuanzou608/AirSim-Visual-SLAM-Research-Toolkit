#!/usr/bin/env python3
import rospy
import rosbag
import cv2
import os
import csv
import numpy as np
from cv_bridge import CvBridge
from sensor_msgs.msg import Image, Imu
from geometry_msgs.msg import Quaternion, Vector3

def main():
    rospy.init_node("bag_creator_stereo_imu", anonymous=True)

    # ---------------------------------------------------
    #  1. CONFIG
    # ---------------------------------------------------
    # Paths (adjust these to your setup)
    imu_csv_path    = "/home/yuan/airsim/data/imu_data.csv"
    left_image_dir  = "/home/yuan/airsim/data/rgb_left_imu"
    right_image_dir = "/home/yuan/airsim/data/rgb_right_imu"
    rosbag_path     = "/home/yuan/airsim/rosbags/stereo_imu/orb_slam3_ros1.bag"

    # If you have a groundtruth file, set it here
    old_gt_path = "/home/yuan/airsim/data/groundtruth.txt"
    new_gt_path = os.path.join(os.path.dirname(rosbag_path), "groundtruth_new.txt")

    # FPS settings
    fps_image = 20
    fps_imu   = 200
    interval_image = 1.0 / fps_image
    interval_imu   = 1.0 / fps_imu

    # ---------------------------------------------------
    #  2. LOAD GROUND TRUTH
    # ---------------------------------------------------
    with open(old_gt_path, 'r') as f:
        lines = f.readlines()

    with open(imu_csv_path, 'r') as f:
        imu_lines = f.readlines()

    old_gt_data = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()  # [timestamp, tx, ty, tz, qx, qy, qz, qw]
        old_gt_data.append(parts)

    new_gt_file = open(new_gt_path, 'w')
    new_gt_file.write("# timestamp tx ty tz qx qy qz qw\n")

    # ---------------------------------------------------
    #  3. GATHER IMAGE FILES (LEFT & RIGHT)
    # ---------------------------------------------------
    def valid_image(f):
        ext = os.path.splitext(f)[1].lower()
        return ext in [".jpg", ".png", ".jpeg", ".bmp", ".tiff"]

    left_files  = sorted([f for f in os.listdir(left_image_dir)  if valid_image(f)])
    right_files = sorted([f for f in os.listdir(right_image_dir) if valid_image(f)])

    num_left  = len(left_files)
    num_right = len(right_files)
    if num_left != num_right:
        rospy.logwarn(f"Left={num_left} images, Right={num_right} images. They are not equal!")
        # Optionally exit or keep the smaller count:
        num_images = min(num_left, num_right)
    else:
        num_images = num_left

    if len(old_gt_data) < len(imu_lines) - 1: # remove title
        rospy.logwarn(f"Ground truth {len(old_gt_data)} has fewer lines than imu data {len(imu_lines)}. Some data won't have GT!")
    elif len(old_gt_data) > len(imu_lines) - 1: # remove title
        rospy.logwarn(f"Ground truth {len(old_gt_data)} has more lines than imu data {len(imu_lines)}. Some GT lines won't be used!")

    # ---------------------------------------------------
    #  4. LOAD IMU CSV
    # ---------------------------------------------------
    # CSV columns:
    #   "timestamp",
    #   "orientation_w","orientation_x","orientation_y","orientation_z",
    #   "angular_velocity_x","angular_velocity_y","angular_velocity_z",
    #   "linear_acceleration_x","linear_acceleration_y","linear_acceleration_z"
    imu_data_list = []
    with open(imu_csv_path, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ow = float(row["orientation_w"])
            ox = float(row["orientation_x"])
            oy = float(row["orientation_y"])
            oz = float(row["orientation_z"])
            avx = float(row["angular_velocity_x"])
            avy = float(row["angular_velocity_y"])
            avz = float(row["angular_velocity_z"])
            lax = float(row["linear_acceleration_x"])
            lay = float(row["linear_acceleration_y"])
            laz = float(row["linear_acceleration_z"])
            imu_data_list.append([ow, ox, oy, oz, avx, avy, avz, lax, lay, laz])

    num_imu = len(imu_data_list)
    # If you expect EXACT ratio of 10 IMU samples per 1 image at 20 vs 200 Hz:
    if num_imu != (10 * num_images):
        rospy.logwarn(f"IMU count {num_imu} != 10 x {num_images}. Check data rates?")

    # ---------------------------------------------------
    #  5. WRITE DATA TO BAG
    # ---------------------------------------------------
    bag = rosbag.Bag(rosbag_path, "w")
    bridge = CvBridge()

    rospy.loginfo("Writing data to rosbag...")
    start_time = rospy.Time.now()

    try:
        for i in range(num_images):
            # 5A) Compute the timestamp for the i-th frame
            ros_time_image = start_time + rospy.Duration(i * interval_image)

            # 5C) READ & WRITE LEFT CAMERA
            left_file = left_files[i]
            left_path = os.path.join(left_image_dir, left_file)
            cv_img_left = cv2.imread(left_path, cv2.IMREAD_COLOR)
            if cv_img_left is not None:
                ros_left = bridge.cv2_to_imgmsg(cv_img_left, encoding="bgr8")
                ros_left.header.stamp = ros_time_image
                bag.write("/camera/left/image_raw", ros_left, ros_time_image)
            else:
                rospy.logwarn(f"Could not read left image: {left_path}")

            # 5D) READ & WRITE RIGHT CAMERA
            right_file = right_files[i]
            right_path = os.path.join(right_image_dir, right_file)
            cv_img_right = cv2.imread(right_path, cv2.IMREAD_COLOR)
            if cv_img_right is not None:
                ros_right = bridge.cv2_to_imgmsg(cv_img_right, encoding="bgr8")
                ros_right.header.stamp = ros_time_image
                bag.write("/camera/right/image_raw", ros_right, ros_time_image)
            else:
                rospy.logwarn(f"Could not read right image: {right_path}")

            # 5E) WRITE IMU SAMPLES FOR THIS FRAME (10 at 200 Hz)
            #     Indices from i*10 to i*10+9
            for j in range(10):
                s = (i + 1) * 10 + j # capture data first capture imu then image
                if s < num_imu:
                    (ow, ox, oy, oz, avx, avy, avz, lax, lay, laz) = imu_data_list[s]
                    ros_time_imu = start_time + rospy.Duration(s * interval_imu)

                    imu_msg = Imu()
                    imu_msg.header.stamp = ros_time_imu
                    imu_msg.orientation = Quaternion(ox, oy, oz, ow)
                    imu_msg.angular_velocity = Vector3(avx, avy, avz)
                    imu_msg.linear_acceleration = Vector3(lax, lay, laz)

                    # Write ground truth (if we have it)
                    # old_gt_data[i] = [old_ts, tx, ty, tz, qx, qy, qz, qw]
                    _, tx, ty, tz, qx, qy, qz, qw = old_gt_data[i * 10 + j]
                    new_timestamp = ros_time_image.to_sec()
                    new_gt_file.write(f"{new_timestamp:.9f} {tx} {ty} {tz} {qx} {qy} {qz} {qw}\n")

                    bag.write("/imu", imu_msg, ros_time_imu)
                else:
                    rospy.logwarn(f"IMU index {s} out of range.")

            if (i + 1) % 100 == 0:
                rospy.loginfo(f"Wrote {i+1} frames => Left & Right + {10*(i+1)} IMU samples")

        rospy.loginfo("Finished writing all data.")
    finally:
        bag.close()
        new_gt_file.close()
        rospy.loginfo(f"Rosbag saved to: {rosbag_path}")
        rospy.loginfo(f"New ground truth saved: {new_gt_path}")


if __name__ == "__main__":
    main()
