import os
import numpy as np
import matplotlib.pyplot as plt
import airsim
import cv2

# Paths
depth_npy_dir = "/home/yuan/airsim/data/depth_left"  # Folder containing .npy depth files
output_png_dir = "/home/yuan/airsim/data/visualize_depth_left"  # New folder for visualized PNG images

# Create output directory if it doesn't exist
os.makedirs(output_png_dir, exist_ok=True)

# List all .npy files
npy_files = sorted([f for f in os.listdir(depth_npy_dir) if f.endswith(".npy")])

# Process each depth file
for npy_file in npy_files:
    # Load depth data
    depth_path = os.path.join(depth_npy_dir, npy_file)
    depth_img = np.load(depth_path)

    # Normalize depth values for visualization
    depth_min = np.min(depth_img)
    depth_max = np.max(depth_img)

    if depth_max > depth_min:  # Avoid division by zero
        # depth_normalized = cv2.normalize(depth_img, None, 0, 255, cv2.NORM_MINMAX)  # check
        depth_normalized = (depth_img - depth_min) / (depth_max - depth_min)  # Normalize to [0,1]
        depth_uint8 = (depth_normalized * 255).astype(np.uint8)  # Convert to [0,255]
    else:
        depth_uint8 = np.zeros_like(depth_img, dtype=np.uint8)  # Black image if all depth is same

    # Save PNG file
    png_filename = npy_file.replace(".npy", ".png")  # Change extension
    png_path = os.path.join(output_png_dir, png_filename)
    airsim.write_png(png_path, depth_uint8)

    # Visualization (optional)
    plt.figure(figsize=(8, 6))
    plt.imshow(depth_uint8, cmap='magma')  # Use 'magma' for better contrast
    plt.colorbar(label="Depth (normalized)")
    plt.title(f"Depth Visualization - {npy_file}")
    plt.axis("off")

    # Save visualization as PNG
    vis_png_path = os.path.join(output_png_dir, "vis_" + png_filename)
    plt.savefig(vis_png_path, bbox_inches='tight', dpi=300)
    plt.close()

    print(f"Processed {npy_file} -> Saved PNG: {png_path}, Visualization: {vis_png_path}")

print("All depth images have been processed and saved.")
