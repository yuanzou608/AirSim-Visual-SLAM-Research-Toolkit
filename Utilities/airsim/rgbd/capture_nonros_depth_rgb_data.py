#!/usr/bin/env python3
import airsim
import numpy as np
import time
import os
import cv2

def capture_nonros_depth_rgb_data():
    # Connect to AirSim
    client = airsim.MultirotorClient()
    client.confirmConnection()

    # Save directory (TUM structure)
    save_dir = "/home/yuan/airsim/data"
    rgb_dir = os.path.join(save_dir, "rgb")
    depth_dir = os.path.join(save_dir, "depth")
    os.makedirs(rgb_dir, exist_ok=True)
    os.makedirs(depth_dir, exist_ok=True)

    # Log files
    rgb_txt = open(os.path.join(save_dir, "rgb.txt"), "w")
    depth_txt = open(os.path.join(save_dir, "depth.txt"), "w")
    gt_txt = open(os.path.join(save_dir, "groundtruth.txt"), "w")
    gt_txt.write("# timestamp tx ty tz qx qy qz qw\n")
    accel_txt = open(os.path.join(save_dir, "accelerometer.txt"), "w")
    accel_txt.write("# timestamp ax ay az\n")
    association_txt = open(os.path.join(save_dir, "associations.txt"), "w")

    # Capture settings
    duration = 320  # seconds
    fps = 20
    interval = 1.0 / fps
    num_frames = duration * fps

    print(f"Capturing {num_frames} frames at {fps} FPS...")

    for i in range(num_frames):
        start_time = time.time()
        timestamp = start_time  # UNIX time in float

        # Get RGB (right) + Depth (left)
        responses = client.simGetImages([
            airsim.ImageRequest("front_right_custom", airsim.ImageType.Scene, False, False),
            airsim.ImageRequest("front_left_custom", airsim.ImageType.DepthPlanar, True)
        ])

        imu = client.getImuData()

        acc = imu.linear_acceleration
        accel_txt.write(f"{timestamp:.6f} {acc.x_val:.6f} {acc.y_val:.6f} {acc.z_val:.6f}\n")

        if len(responses) != 2 or any(r.height == 0 for r in responses):
            print(f"Frame {i}: Empty image, skipping.")
            continue

        # Decode RGB
        rgb_resp = responses[0]
        rgb_img = np.frombuffer(rgb_resp.image_data_uint8, dtype=np.uint8)
        rgb_img = rgb_img.reshape(rgb_resp.height, rgb_resp.width, 3)

        # Decode Depth
        depth_resp = responses[1]
        depth_img = np.array(depth_resp.image_data_float, dtype=np.float32)
        depth_img = depth_img.reshape(depth_resp.height, depth_resp.width)
        depth_img_mm = (depth_img * 1000).astype(np.uint16)

        # Filenames (timestamp as name)
        ts_str = f"{timestamp:.6f}"
        rgb_filename = f"{ts_str}.png"
        depth_filename = f"{ts_str}.png"

        # Save images
        airsim.write_png(os.path.join(rgb_dir, rgb_filename), rgb_img)
        cv2.imwrite(os.path.join(depth_dir, depth_filename), depth_img_mm)

        # Log timestamps
        rgb_txt.write(f"{ts_str} rgb/{rgb_filename}\n")
        depth_txt.write(f"{ts_str} depth/{depth_filename}\n")

        # Log association
        association_txt.write(f"{ts_str} rgb/{rgb_filename} {ts_str} depth/{depth_filename}\n")


        # Log ground truth
        pose = client.simGetVehiclePose()
        p = pose.position
        o = pose.orientation
        gt_txt.write(f"{ts_str} {p.x_val:.6f} {p.y_val:.6f} {p.z_val:.6f} "
                     f"{o.x_val:.6f} {o.y_val:.6f} {o.z_val:.6f} {o.w_val:.6f}\n")

        # Progress
        if i % fps == 0:
            print(f"Saved frame {i} at timestamp {ts_str}")

        # Maintain frame rate
        elapsed = time.time() - start_time
        time.sleep(max(0, interval - elapsed))

    # Cleanup
    rgb_txt.close()
    depth_txt.close()
    gt_txt.close()
    accel_txt.close()
    association_txt.close()

    print("✅ Done! TUM-format dataset saved at:", save_dir)

if __name__ == "__main__":
    capture_nonros_depth_rgb_data()