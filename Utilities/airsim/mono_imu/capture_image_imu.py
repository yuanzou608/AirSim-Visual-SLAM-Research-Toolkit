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
rgb_left_dir      = os.path.join(save_dir, "rgb_left")
rgb_right_dir     = os.path.join(save_dir, "rgb_right")
depth_left_dir    = os.path.join(save_dir, "depth_left")
imu_csv_path      = os.path.join(save_dir, "imu_data.csv")

# Desired real-time capture rates
imu_rate_hz       = 200.0  # IMU frequency
image_rate_hz     = 20.0   # Image frequency
capture_duration  = 30.0   # Seconds to capture data

# Make directories
os.makedirs(rgb_center_dir, exist_ok=True)
os.makedirs(rgb_left_dir, exist_ok=True)
os.makedirs(rgb_right_dir, exist_ok=True)
os.makedirs(depth_left_dir, exist_ok=True)

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
    "orientation_w",        # from getImuData()
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
# For real-time capture, we’ll run at the highest frequency (200 Hz) and
# sample images on every 10th iteration → 20 Hz.

imu_period        = 1.0 / imu_rate_hz     # 0.005 sec
image_period      = 1.0 / image_rate_hz   # 0.05 sec
image_step_count  = int(imu_rate_hz / image_rate_hz)  # should be 10 if 200/20

num_iterations    = int(capture_duration * imu_rate_hz)

print(f"Capturing IMU at {imu_rate_hz} Hz and images at {image_rate_hz} Hz for {capture_duration} seconds.")
print(f"Total IMU samples ~ {num_iterations}, total images ~ {int(capture_duration * image_rate_hz)}.")

# Start takeoff (if needed)
client.takeoffAsync()

start_script_time = time.time()

# -----------------------
#        MAIN LOOP
# -----------------------
for i in range(num_iterations):
    loop_start_time = time.time()
    elapsed = loop_start_time - start_script_time

    # -------------------
    #       IMU
    # -------------------
    imu_data = client.getImuData()
    if imu_data is not None:
        # Write row to CSV
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

    # -------------------
    #     IMAGES?
    # -------------------
    # Grab images once every image_step_count iterations
    if (i % image_step_count) == 0:
        responses = client.simGetImages([
            airsim.ImageRequest("front_center_custom", airsim.ImageType.Scene, False, False),
            airsim.ImageRequest("front_left_custom",   airsim.ImageType.Scene, False, False),
            airsim.ImageRequest("front_right_custom",  airsim.ImageType.Scene, False, False),
            airsim.ImageRequest("front_left_custom",   airsim.ImageType.DepthPlanar, True)
        ])

        # Validate we got 4 responses
        if len(responses) == 4:
            rgb_center_response, rgb_left_response, rgb_right_response, depth_left_response = responses
            if (rgb_center_response.height > 0 and rgb_center_response.width > 0 and
                rgb_left_response.height > 0   and rgb_left_response.width > 0   and
                rgb_right_response.height > 0  and rgb_right_response.width > 0  and
                depth_left_response.height > 0 and depth_left_response.width > 0):


                # Convert center
                rgb_center_img1d = np.frombuffer(rgb_center_response.image_data_uint8, dtype=np.uint8)
                rgb_center_img   = rgb_center_img1d.reshape(rgb_center_response.height, rgb_center_response.width, 3)
                # Convert left
                rgb_left_img1d   = np.frombuffer(rgb_left_response.image_data_uint8, dtype=np.uint8)
                rgb_left_img     = rgb_left_img1d.reshape(rgb_left_response.height, rgb_left_response.width, 3)
                # Convert right
                rgb_right_img1d  = np.frombuffer(rgb_right_response.image_data_uint8, dtype=np.uint8)
                rgb_right_img    = rgb_right_img1d.reshape(rgb_right_response.height, rgb_right_response.width, 3)
                # Convert depth
                depth_left_img1d = np.array(depth_left_response.image_data_float, dtype=np.float32)
                depth_left_img   = depth_left_img1d.reshape(depth_left_response.height, depth_left_response.width)

                # Generate filenames
                image_index          = i // image_step_count
                rgb_center_filename  = os.path.join(rgb_center_dir,  f"frame_{image_index:06d}.png")
                rgb_left_filename    = os.path.join(rgb_left_dir,    f"frame_{image_index:06d}.png")
                rgb_right_filename   = os.path.join(rgb_right_dir,   f"frame_{image_index:06d}.png")
                depth_left_filename  = os.path.join(depth_left_dir,  f"depth_{image_index:06d}.npy")

                # Save
                airsim.write_png(rgb_center_filename, rgb_center_img)
                airsim.write_png(rgb_left_filename,   rgb_left_img)
                airsim.write_png(rgb_right_filename,  rgb_right_img)
                np.save(depth_left_filename, depth_left_img)

                # Print progress occasionally
                if (image_index % int(image_rate_hz)) == 0:
                    print(f"[{elapsed:.2f}s] Saved images => {rgb_center_filename}")
            else:
                print(f"Skipping frame {i}: Invalid image data (0×0).")
        else:
            print(f"Skipping frame {i}: Incomplete image responses (got {len(responses)}).")

    # -------------------
    #    DRONE MOTION?
    # -------------------
    # Example: Move the drone after 5 seconds
    if abs(elapsed - 5.0) < 0.1:  # ~5s mark
        # Move the drone for remainder of duration
        # (the velocity command below is just an example)
        print("[5s mark] Moving drone...")
        client.moveByVelocityAsync(0, -0.2, 0, capture_duration * (int(image_rate_hz//6 + 1))) # we will "compress" the images into a rosbag

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

print("Capture completed.")
print(f"IMU data saved to: {imu_csv_path}")
print(f"Images saved under: {save_dir}")
