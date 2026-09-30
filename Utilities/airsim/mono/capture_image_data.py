#!/usr/bin/env python3
import airsim
import numpy as np
import time
import os

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# Directory for saving images
save_dir = "/home/yuan/airsim/data/"
rgb_center_dir = os.path.join(save_dir, "rgb_center")
rgb_left_dir = os.path.join(save_dir, "rgb_left")
rgb_right_dir = os.path.join(save_dir, "rgb_right")
depth_left_dir = os.path.join(save_dir, "depth_left_raw")

os.makedirs(rgb_center_dir, exist_ok=True)
os.makedirs(rgb_left_dir, exist_ok=True)
os.makedirs(rgb_right_dir, exist_ok=True)
os.makedirs(depth_left_dir, exist_ok=True)

# -- Ground truth file (TUM format) ------------------------------------
# We’ll store: timestamp tx ty tz qx qy qz qw
tum_file_path = os.path.join(save_dir, "groundtruth.txt")  # <-- ADDED
tum_file = open(tum_file_path, "w")  # <-- ADDED
tum_file.write("# timestamp tx ty tz qx qy qz qw\n")  # <-- ADDED
# ----------------------------------------------------------------------

# Capture settings
duration = 120  # Total seconds
fps = 20  # Frames per second
interval = 1.0 / fps  # Time interval between frames
num_images = fps * duration  # Total images

print(f"Capturing {num_images} images over {duration} seconds...")


for i in range(num_images):
    start_time = time.time()

    # Capture RGB and Depth images
    responses = client.simGetImages([
        airsim.ImageRequest("front_center_custom", airsim.ImageType.Scene, False, False),
        airsim.ImageRequest("front_left_custom", airsim.ImageType.Scene, False, False),
        airsim.ImageRequest("front_right_custom", airsim.ImageType.Scene, False, False),
        airsim.ImageRequest("front_left_custom", airsim.ImageType.DepthPlanar, True)

    ])

    # validate the length of responses
    if len(responses) != 4:
        print(f"Skipping frame {i}: Incomplete image responses received")
        continue

    rgb_center_response = responses[0]
    rgb_left_response = responses[1]
    rgb_right_response = responses[2]
    depth_left_response = responses[3]

    # Validate images
    if rgb_center_response.height == 0 or rgb_center_response.width == 0:
        print(f"Skipping frame {i}: Invalid RGB center image received")
        continue
    if rgb_left_response.height == 0 or rgb_left_response.width == 0:
        print(f"Skipping frame {i}: Invalid RGB left image received")
        continue
    if rgb_right_response.height == 0 or rgb_right_response.width == 0:
        print(f"Skipping frame {i}: Invalid RGB right image received")
        continue
    if depth_left_response.height == 0 or depth_left_response.width == 0:
        print(f"Skipping frame {i}: Invalid Depth image received")
        continue

    # Process RGB Image (Raw uint8 format)
    rgb_center_img1d = np.frombuffer(rgb_center_response.image_data_uint8, dtype=np.uint8)
    rgb_center_img = rgb_center_img1d.reshape(rgb_center_response.height, rgb_center_response.width, 3)

    rgb_left_img1d = np.frombuffer(rgb_left_response.image_data_uint8, dtype=np.uint8)
    rgb_left_img = rgb_left_img1d.reshape(rgb_left_response.height, rgb_left_response.width, 3)

    rgb_right_img1d = np.frombuffer(rgb_right_response.image_data_uint8, dtype=np.uint8)
    rgb_right_img = rgb_right_img1d.reshape(rgb_right_response.height, rgb_right_response.width, 3)

    # Process Depth Image (Raw 32-bit float)
    depth_left_img1d = np.array(depth_left_response.image_data_float, dtype=np.float32)
    depth_left_img = depth_left_img1d.reshape(depth_left_response.height, depth_left_response.width)

    # Save images in RAW format
    rgb_center_filename = os.path.join(rgb_center_dir, f"frame_{i:06d}.png")
    rgb_left_filename = os.path.join(rgb_left_dir, f"frame_{i:06d}.png")
    rgb_right_filename = os.path.join(rgb_right_dir, f"frame_{i:06d}.png")
    depth_left_filename = os.path.join(depth_left_dir, f"depth_{i:06d}.npy")  # .npy for depth

    airsim.write_png(os.path.normpath(rgb_center_filename), rgb_center_img)
    airsim.write_png(os.path.normpath(rgb_left_filename), rgb_left_img)
    airsim.write_png(os.path.normpath(rgb_right_filename), rgb_right_img)
    np.save(depth_left_filename, depth_left_img)

    # Print saved file info every second
    if i % fps == 0:
        print(f"Saved RGB: {rgb_center_filename}")

    # --- Get and record ground-truth pose in TUM format ------------------
    kinematics = client.simGetGroundTruthKinematics()  # <-- ADDED
    pos = kinematics.position  # <-- ADDED
    orn = kinematics.orientation  # <-- ADDED
    # Write out: timestamp x y z qx qy qz qw
    tum_file.write(f"{start_time:.6f} {pos.x_val} {pos.y_val} {pos.z_val} "
                   f"{orn.x_val} {orn.y_val} {orn.z_val} {orn.w_val}\n")  # <-- ADDED
    # ---------------------------------------------------------------------


    # Wait until the next frame time
    elapsed_time = time.time() - start_time
    sleep_time = max(0, interval - elapsed_time)
    time.sleep(sleep_time)



# Close the TUM file
tum_file.close()  # <-- ADDED

print("Image capture completed. Ground-truth TUM data saved:", tum_file_path)
