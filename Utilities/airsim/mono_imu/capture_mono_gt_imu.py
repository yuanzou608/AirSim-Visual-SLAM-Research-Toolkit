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
rgb_center_dir    = os.path.join(save_dir, "rgb_center")
imu_csv_path      = os.path.join(save_dir, "imu_data.csv")
tum_file_path     = os.path.join(save_dir, "groundtruth.txt")
tum_file          = open(tum_file_path, "w")
tum_file.write("# timestamp tx ty tz qx qy qz qw\n")

# Desired real-time capture rates
imu_rate_hz       = 200.0  # "IMU" frequency, but now we'll log GT kinematics
image_rate_hz     = 20.0   # Image frequency
capture_duration  = 45.0   # Seconds to capture data

# Make directories
os.makedirs(rgb_center_dir, exist_ok=True)

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

# -----------------------
#   PREPARE CAPTURE LOOP
# -----------------------
imu_period        = 1.0 / imu_rate_hz     # 0.005 sec
image_period      = 1.0 / image_rate_hz   # 0.05 sec
image_step_count  = int(imu_rate_hz / image_rate_hz)  # should be 10 if 200/20

num_iterations    = int(capture_duration * imu_rate_hz)

print(f"Capturing 'IMU' (GT) at {imu_rate_hz} Hz and images at {image_rate_hz} Hz for {capture_duration} seconds.")
print(f"Total 'IMU' samples ~ {num_iterations}, total images ~ {int(capture_duration * image_rate_hz)}.")

start_script_time = time.time()
move_triggered = False

# -----------------------
#        MAIN LOOP
# -----------------------
for i in range(num_iterations):
    loop_start_time = time.time()
    elapsed = loop_start_time - start_script_time

    # --- Get and record ground-truth pose in TUM format ------------------
    kinematics = client.simGetGroundTruthKinematics()
    pos = kinematics.position
    orn = kinematics.orientation
    tum_file.write(f"{loop_start_time:.6f} {pos.x_val} {pos.y_val} {pos.z_val} "
                   f"{orn.x_val} {orn.y_val} {orn.z_val} {orn.w_val}\n")
    # ---------------------------------------------------------------------

    # -------------------
    #  Ground-Truth "IMU"
    # -------------------
    gt_orn = kinematics.orientation
    gt_ang_vel = kinematics.angular_velocity
    gt_lin_acc = kinematics.linear_acceleration

    imu_csv_writer.writerow([
        f"{elapsed:.6f}",
        gt_orn.w_val,
        gt_orn.x_val,
        gt_orn.y_val,
        gt_orn.z_val,
        gt_ang_vel.x_val,
        gt_ang_vel.y_val,
        gt_ang_vel.z_val,
        gt_lin_acc.x_val,
        gt_lin_acc.y_val,
        gt_lin_acc.z_val
    ])

    # -------------------
    #     IMAGES?
    # -------------------
    if (i % image_step_count) == 0:
        responses = client.simGetImages([
            airsim.ImageRequest("front_center_custom", airsim.ImageType.Scene, False, False)
        ])

        if len(responses) == 1:
            rgb_center_response = responses[0]
            if rgb_center_response.height > 0 and rgb_center_response.width > 0:
                rgb_center_img1d = np.frombuffer(rgb_center_response.image_data_uint8, dtype=np.uint8)
                rgb_center_img   = rgb_center_img1d.reshape(rgb_center_response.height,
                                                            rgb_center_response.width, 3)
                image_index          = i // image_step_count
                rgb_center_filename  = os.path.join(rgb_center_dir, f"frame_{image_index:06d}.png")
                airsim.write_png(os.path.normpath(rgb_center_filename), rgb_center_img)

                # Print progress occasionally
                if (image_index % int(image_rate_hz)) == 0:
                    print(f"[{elapsed:.2f}s] Saved images => {rgb_center_filename}")
            else:
                print(f"Skipping frame {i}: Invalid image data (0×0).")
        else:
            print(f"Skipping frame {i}: Incomplete image responses (got {len(responses)}).")


    # -------------------
    #   SLEEP TO KEEP RATE
    # -------------------
    loop_end_time = time.time()
    loop_elapsed  = loop_end_time - loop_start_time
    sleep_time    = imu_period - loop_elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)

# -----------------------
#       WRAP UP
# -----------------------
print("Stopping drone and landing...")
client.hoverAsync().join()
time.sleep(2)
client.landAsync().join()

client.armDisarm(False)
client.enableApiControl(False)
imu_csv_file.close()
tum_file.close()

print("Capture completed.")
print(f"GT-based 'IMU' data saved to: {imu_csv_path}")
print(f"Images saved under: {save_dir}")
print(f"Ground-truth TUM data saved to: {tum_file_path}")
