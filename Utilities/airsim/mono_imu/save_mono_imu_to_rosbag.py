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
    rospy.init_node("bag_creator_simple", anonymous=True)

    # ---------------------------------------------------
    #  1. CONFIG
    # ---------------------------------------------------
    # Paths (adjust these to your setup)
    imu_csv_path = "/home/yuan/airsim/data/imu_data.csv"
    image_dir = "/home/yuan/airsim/data/rgb_left"
    rosbag_path = "/home/yuan/airsim/rosbags/mono_imu/orb_slam3_ros1.bag"

    # FPS setting
    fps_image = 20
    fps_imu = 200
    interval_image = 1.0 / fps_image
    interval_imu = 1.0 / fps_imu

    # We assume total 60 seconds at:
    #   - 20 FPS => 1200 images
    #   - 200 Hz => 12000 IMU samples
    # count images
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
    num_images = len([file for file in os.listdir(image_dir) if file.lower().endswith(tuple(image_extensions))])

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

    # count imu date
    imu_list = []
    with open(imu_csv_path, 'r') as csvfile:
        csv_reader = csv.reader(csvfile, delimiter=',')
        header = next(csv_reader)
        num_imu = sum(1 for _ in csv_reader)

    # check alignment
    if num_imu != 10 * num_images:
        rospy.logerr("Mismatch: we expect exactly 10 IMU samples per image!")
        return

    # A tiny offset so no two timestamps are exactly equal
    epsilon = 0

    # ---------------------------------------------------
    #  2. LOAD IMU CSV (12000 rows expected)
    # ---------------------------------------------------
    # CSV columns (as per your AirSim capture):
    #   timestamp, orientation_w, orientation_x, orientation_y, orientation_z,
    #   angular_velocity_x, angular_velocity_y, angular_velocity_z,
    #   linear_acceleration_x, linear_acceleration_y, linear_acceleration_z
    imu_data_list = []
    with open(imu_csv_path, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            t = float(row["timestamp"])
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

    if len(imu_data_list) != num_imu:
        rospy.logwarn(f"Expected {num_imu} IMU rows, but got {len(imu_data_list)} in CSV.")

    # We ignore the CSV's original 'timestamp' here,
    # because we'll assign *synthetic* times (0..60s).
    # If you wanted real flight times, you'd adapt differently.

    # ---------------------------------------------------
    #  3. GATHER IMAGES (1200 images expected)
    # ---------------------------------------------------
    image_files = sorted([f for f in os.listdir(image_dir) if f.endswith(".png")])
    if len(image_files) != num_images:
        rospy.logwarn(f"Expected {num_images} images, but found {len(image_files)} in {image_dir}")

    # ---------------------------------------------------
    #  4. WRITE TO BAG
    # ---------------------------------------------------
    bag = rosbag.Bag(rosbag_path, "w")
    bridge = CvBridge()

    try:
        rospy.loginfo("Writing data to rosbag...")

        # For each image i => timestamp = i * 0.05 sec
        # Then 10 IMU entries => s = i*10 .. i*10+9
        # IMU time => i*0.05 + (j+1)*0.005 - epsilon
        # => from [ i*0.05 + 0.005 ] up to [ i*0.05 + 0.05 ] minus epsilon
        # Ensures strictly ascending order with next image.
        #
        # Example: i=0 => image time=0.0, IMU times= [0.005-eps, 0.01-eps, ... 0.05-eps]
        # Next image i=1 => time=0.05 => bigger than 0.05-eps => safe.

        start_time = rospy.Time.now()  # Start time reference

        for i in range(num_images):
            # t_img = i * 0.05  # 20 FPS from t=0..59.95
            # stamp_img = rospy.Time.from_sec(t_img)
            ros_time_image = start_time + rospy.Duration(i * interval_image)
            # Write ground truth line (if available)
            if i < len(old_gt_data):
                # old_gt_data[i] = [old_ts, tx, ty, tz, qx, qy, qz, qw]
                _, tx, ty, tz, qx, qy, qz, qw = old_gt_data[i]
                new_timestamp = ros_time_image.to_sec()
                new_gt_file.write(f"{new_timestamp:.9f} {tx} {ty} {tz} {qx} {qy} {qz} {qw}\n")
            # -------------------------------------------------
            # A) Write image
            # -------------------------------------------------
            # Read the i-th image
            img_file = image_files[i] if i < len(image_files) else None
            if img_file is not None:
                path_img = os.path.join(image_dir, img_file)
                cv_image = cv2.imread(path_img, cv2.IMREAD_COLOR)
                if cv_image is not None:
                    ros_image = bridge.cv2_to_imgmsg(cv_image, encoding="bgr8")
                    ros_image.header.stamp = ros_time_image
                    bag.write("/camera/image_raw", ros_image, ros_time_image)
                else:
                    rospy.logwarn(f"Failed to read {path_img}. Skipping image.")
            else:
                rospy.logwarn(f"No image file at index {i}, skipping.")

            # -------------------------------------------------
            # B) Write the 10 IMU samples that go with this image
            # -------------------------------------------------
            for j in range(10):
                s = (i + 1) * 10 + j  # capture data from imu first then image
                # Synthetic time for IMU sample
                #  from 0.005..0.05 within the same 50ms chunk
                # t_imu = (i * 0.05) + ((j + 1) * 0.005) - epsilon
                # stamp_imu = rospy.Time.from_sec(t_imu)
                ros_time_imu = start_time + rospy.Duration(s * interval_imu)

                if s < len(imu_data_list):
                    (ow, ox, oy, oz, avx, avy, avz, lax, lay, laz) = imu_data_list[s]
                    imu_msg = Imu()
                    imu_msg.header.stamp = ros_time_imu
                    imu_msg.orientation = Quaternion(ox, oy, oz, ow)
                    imu_msg.angular_velocity = Vector3(avx, avy, avz)
                    imu_msg.linear_acceleration = Vector3(lax, lay, laz)

                    bag.write("/imu", imu_msg, ros_time_imu)
                else:
                    rospy.logwarn(f"IMU index {s} out of range. Skipping.")

            if (i + 1) % 100 == 0:
                rospy.loginfo(f"Wrote {i + 1} images (and {10 * (i + 1)} IMU samples).")

        rospy.loginfo("Finished writing all data.")

    finally:
        bag.close()
        new_gt_file.close()
        rospy.loginfo(f"Rosbag saved to: {rosbag_path}")
        rospy.loginfo(f"New ground truth saved: {new_gt_path}")


if __name__ == "__main__":
    main()
