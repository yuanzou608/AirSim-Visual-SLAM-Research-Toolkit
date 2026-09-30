import matplotlib.pyplot as plt
import numpy as np
import cv2

# Load the depth image from a PNG file
depth_path = "4348.794000.png"
depth_image = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)  # Preserve original bit-depth

if depth_image is None:
    raise ValueError(f"Cannot load image from {depth_path}")

# Convert to float32 if not already (e.g., if uint16 is used, and values represent millimeters)
if depth_image.dtype != np.float32:
    depth_image = depth_image.astype(np.float32)
    # Optional: scale to meters if needed (e.g., divide by 1000 if stored in millimeters)
    # depth_image /= 1000.0

# Avoid extremely large distances (clamp depth > 300 to 300)
depth_image[depth_image > 50] = 50

# Normalize depth for visualization
depth_min = np.min(depth_image)
depth_max = np.max(depth_image)

if depth_max > depth_min:
    depth_normalized = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX)
    depth_8bit = depth_normalized.astype(np.uint8)
else:
    depth_8bit = np.zeros_like(depth_image, dtype=np.uint8)

# Convert to BGR for cv2-based visualization (optional, for saving)
depth_vis = cv2.cvtColor(depth_8bit, cv2.COLOR_GRAY2BGR)

# Plotting
plt.figure(figsize=(12, 5))

# Subplot 1: Depth Image Visualization
plt.subplot(1, 2, 1)
plt.imshow(depth_8bit, cmap='jet')  # Use colormap for better visual contrast
plt.colorbar(label="Depth (Normalized)")
plt.title("Depth Image Visualization")
plt.axis("off")

# Subplot 2: Histogram of Depth Values
plt.subplot(1, 2, 2)
plt.hist(depth_image.flatten(), bins=50, color='blue', alpha=0.7)
plt.xlabel("Depth Value")
plt.ylabel("Frequency")
plt.title("Histogram of Depth Values")

plt.tight_layout()
plt.show()
