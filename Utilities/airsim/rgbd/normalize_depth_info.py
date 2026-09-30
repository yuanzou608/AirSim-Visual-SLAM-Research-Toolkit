import os
import numpy as np
import cv2

# Paths
input_folder = "/home/yuan/airsim/data/depth_left_raw"  # Folder with .npy files
output_folder = "/home/yuan/airsim/data/depth_left"  # Folder to save grayscale images

# Ensure output folder exists
os.makedirs(output_folder, exist_ok=True)

# Get list of all .npy files
depth_files = sorted([f for f in os.listdir(input_folder) if f.endswith(".npy")])

# Process each depth file
for i, depth_file in enumerate(depth_files):
    # Load depth image
    depth_path = os.path.join(input_folder, depth_file)
    depth_image = np.load(depth_path).astype(np.float32)  # Ensure float32 precision

    # Avoid infinite distance
    depth_image[depth_image > 100] = 100  # Clamp max depth

    # Normalize depth values to range [0, 65535] for 16-bit PNG (higher precision)
    depth_normalized = cv2.normalize(depth_image, None, 0, 65535, cv2.NORM_MINMAX) # check 
    depth_uint16 = depth_normalized.astype(np.uint16)  # Convert to uint16 for grayscale depth storage

    # # Normalize depth values to 8-bit for visualization
    # depth_normalized = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX)
    # depth_8bit = depth_normalized.astype(np.uint8)

    # Save depth image as 16-bit PNG (higher precision for depth)
    output_path = os.path.join(output_folder, depth_file.replace(".npy", ".png"))
    cv2.imwrite(output_path, depth_uint16)

    if i % 100 == 0:
        print(f"Saved: {output_path}")

print("\nAll depth images have been processed and saved successfully!")
