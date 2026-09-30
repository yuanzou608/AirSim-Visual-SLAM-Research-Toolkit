#!/usr/bin/env python3
import airsim
import numpy as np
import time
import os
import csv

# -----------------------
#       CONFIG
# -----------------------
save_dir          = "/home/yuan/airsim/data/"
rgb_left_dir      = os.path.join(save_dir, "rgb_left_imu")
rgb_right_dir     = os.path.join(save_dir, "rgb_right_imu")
imu_csv_path      = os.path.join(save_dir, "imu_data.csv")
tum_file_path     = os.path.join(save_dir, "groundtruth.txt")

# Desired real-time capture rates
imu_rate_hz       = 200.0  # IMU frequency
image_rate_hz     = 20.0   # Image frequency
capture_duration  = 80.0   # Seconds to capture data

# Make directories for images
os.makedirs(rgb_left_dir, exist_ok=True)
os.makedirs(rgb_right_dir, exist_ok=True)

# TUM format ground truth file
tum_file = open(tum_file_path, "w")
tum_file.write("# timestamp tx ty tz qx qy qz qw\n")

# -----------------------
#    CONNECT TO AIRSIM
# -----------------------
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# -----------------------
#   SET UP FILE OUTPUTS
# -----------------------
# CSV for IMU data
imu_csv_file = open(imu_csv_path, mode='w', newline='')
imu_csv_writer = csv.writer(imu_csv_file)
imu_csv_writer.writerow([
    "timestamp",            # float seconds since script start
    "orientation_w",
    "orientation_x",
    "orientation_y",
    "orientation_z",
    "angular_velocity_x",
    "angular_velocity_y",
    "angular_velocity_z",
    "linear_acceleration_x",
    "linear_acceleration_y",
    "linear_acceleration_z"
])

# We’ll run at the highest frequency (200 Hz) for IMU
# and capture images every 10th iteration → 20 Hz
imu_period       = 1.0 / imu_rate_hz     # 0.005 sec
image_period     = 1.0 / image_rate_hz   # 0.05 sec
image_step_count = int(imu_rate_hz / image_rate_hz)  # 200/20 = 10
num_iterations   = int(capture_duration * imu_rate_hz)

print(f"Capturing IMU at {imu_rate_hz} Hz and images at {image_rate_hz} Hz for {capture_duration} seconds.")
print(f"Total IMU samples ~ {num_iterations}, total images ~ {int(capture_duration * image_rate_hz)}.")

start_script_time = time.time()

# -----------------------
#        MAIN LOOP
# -----------------------
for i in range(num_iterations):
    loop_start_time = time.time()
    elapsed = loop_start_time - start_script_time

    # --- Ground-truth pose in TUM format ---
    kinematics = client.simGetGroundTruthKinematics()
    pos = kinematics.position
    orn = kinematics.orientation
    # timestamp x y z qx qy qz qw
    tum_file.write(f"{loop_start_time:.6f} {pos.x_val} {pos.y_val} {pos.z_val} "
                   f"{orn.x_val} {orn.y_val} {orn.z_val} {orn.w_val}\n")

    # --- IMU ---
    imu_data = client.getImuData()
    if imu_data is not None:
        imu_csv_writer.writerow([
            f"{elapsed:.6f}",
            imu_data.orientation.w_val,
            imu_data.orientation.x_val,
            imu_data.orientation.y_val,
            imu_data.orientation.z_val,
            imu_data.angular_velocity.x_val,
            imu_data.angular_velocity.y_val,
            imu_data.angular_velocity.z_val,
            imu_data.linear_acceleration.x_val,
            imu_data.linear_acceleration.y_val,
            imu_data.linear_acceleration.z_val
        ])

    # --- Images? ---
    # Capture images once every image_step_count iterations
    if (i % image_step_count) == 0:
        image_index = i // image_step_count

        # Request both LEFT and RIGHT images in one call
        responses = client.simGetImages([
            airsim.ImageRequest("front_left_custom",  airsim.ImageType.Scene, False, False),
            airsim.ImageRequest("front_right_custom", airsim.ImageType.Scene, False, False)
        ])

        # We expect 2 responses for stereo
        if len(responses) == 2:
            left_resp  = responses[0]
            right_resp = responses[1]

            # Validate we got valid images
            if left_resp.height > 0 and left_resp.width > 0 and \
               right_resp.height > 0 and right_resp.width > 0:

                # Convert LEFT image
                left_img1d = np.frombuffer(left_resp.image_data_uint8, dtype=np.uint8)
                left_img   = left_img1d.reshape(left_resp.height, left_resp.width, 3)

                # Convert RIGHT image
                right_img1d = np.frombuffer(right_resp.image_data_uint8, dtype=np.uint8)
                right_img   = right_img1d.reshape(right_resp.height, right_resp.width, 3)

                # Build filenames
                left_filename  = os.path.join(rgb_left_dir,  f"frame_{image_index:06d}.png")
                right_filename = os.path.join(rgb_right_dir, f"frame_{image_index:06d}.png")

                # Save images
                airsim.write_png(os.path.normpath(left_filename),  left_img)
                airsim.write_png(os.path.normpath(right_filename), right_img)

                # Print progress occasionally
                if (image_index % int(image_rate_hz)) == 0:
                    print(f"[{elapsed:.2f}s] Saved stereo pair =>")
                    print(f"    LEFT : {left_filename}")
                    print(f"    RIGHT: {right_filename}")
            else:
                print(f"Skipping frame {i}: Invalid image data (0×0).")
        else:
            print(f"Skipping frame {i}: Expected 2 images, got {len(responses)}.")


    # --- Keep the rate at 200 Hz ---
    loop_end_time = time.time()
    loop_elapsed = loop_end_time - loop_start_time
    sleep_time = imu_period - loop_elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)


imu_csv_file.close()
tum_file.close()

print("Capture completed.")
print(f"IMU data saved to: {imu_csv_path}")
print(f"Images saved under: {save_dir}")
print("Ground-truth TUM data saved:", tum_file_path)
