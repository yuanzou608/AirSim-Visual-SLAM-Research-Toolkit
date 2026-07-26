import airsim
import numpy as np
import csv
import matplotlib.pyplot as plt
# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()

# Get depth image
responses = client.simGetImages([
    airsim.ImageRequest("front_left_custom", airsim.ImageType.DepthPlanar, True),
    airsim.ImageRequest("front_left_custom", airsim.ImageType.Scene, False, False),
])
depth_image = responses[0]  # Get the first (and only) response
rgb_image = responses[1]
# Convert depth data to numpy array
depth_array = np.array(depth_image.image_data_float, dtype=np.float32)
depth_array = depth_array.reshape(depth_image.height, depth_image.width)
rgb_array = np.frombuffer(rgb_image.image_data_uint8, dtype=np.uint8)
rgb_array = rgb_array.reshape(depth_image.height, depth_image.width, 3)

np.save("depth_example.npy", depth_array)


# Save to CSV
with open("depth.csv", "w", newline='') as f:
    writer = csv.writer(f)
    for row in depth_array:
        writer.writerow(row)

# Visualize depth image with depth values on pixels
plt.figure(figsize=(10, 8))
plt.imshow(depth_array, cmap='gray')
plt.colorbar(label='Depth (m)')
plt.title("Depth Image from AirSim (with Depth Values)")

# Add depth values as text on image
height, width = depth_array.shape
step = max(1, int(width / 50))  # control how dense the text overlay is
# step = 1
for y in range(0, height, step):
    for x in range(0, width, step):
        depth_value = round(depth_array[y, x], 1)
        depth_value_int = int(depth_value)
        plt.text(x, y, str(depth_value_int), fontsize=5, color='red', ha='center', va='center')

plt.axis('off')
plt.tight_layout()

# Save image
plt.savefig("depth_image_with_values.png", dpi=300)
plt.show()

print("Saved annotated depth image to 'depth_image_with_values.png'")

plt.imshow(rgb_array, cmap='gray')
for y in range(0, height, step):
    for x in range(0, width, step):
        depth_value = round(depth_array[y, x], 1)
        depth_value_int = int(depth_value)
        plt.text(x, y, str(depth_value_int), fontsize=5, color='red', ha='center', va='center')

plt.axis('off')
plt.tight_layout()
plt.savefig("rgb_image_with_values.png", dpi=300)
plt.show()

depth = np.load("depth_example.npy")
print(depth)