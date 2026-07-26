import airsim
import cv2
import numpy as np
import time

# Connect to AirSim running inside Docker
client = airsim.MultirotorClient(ip="127.0.0.1")  # Change IP if needed
client.confirmConnection()

# Set up video properties
frame_width = 672  # Match settings.json
frame_height = 376
fps = 30  # Frames per second

directory = '/home/yuan/airsim/videos/airsim_output.avi'
# OpenCV Video Writer to save output (optional)
out = cv2.VideoWriter(directory, cv2.VideoWriter_fourcc(*'XVID'), fps, (frame_width, frame_height))

print("Press 'q' to stop recording...")

# Start video capture loop
while True:
    # Capture an image from the front_center_custom camera
    requests = [airsim.ImageRequest("front_left_custom",
                                    airsim.ImageType.DepthPlanar,
                                    pixels_as_float=True,
                                    compress=False)]


    # Convert response to an image
    responses = client.simGetImages(requests)
    if responses and responses[0].image_data_float:
        # Convert the float32 depth buffer to a NumPy array
        depth_data = np.array(responses[0].image_data_float, dtype=np.float32)

        # Reshape so it's [height x width]
        depth_image = depth_data.reshape(responses[0].height, responses[0].width)
        depth_image[depth_image > 100] = 50

        # To avoid extreme values dominating, clamp (clip) using, e.g., 5th/95th percentiles
        low_val = np.percentile(depth_image, 5)  # 5% depth
        high_val = np.percentile(depth_image, 95)  # 95% depth
        depth_clamped = np.clip(depth_image, low_val, high_val)

        # Now normalize clamped depth to [0..255]
        depth_normalized = cv2.normalize(depth_clamped, None, 0, 255, cv2.NORM_MINMAX)
        depth_8bit = depth_normalized.astype(np.uint8)

        # Convert to BGR for imshow
        depth_vis = cv2.cvtColor(depth_8bit, cv2.COLOR_GRAY2BGR)
        cv2.imshow("Depth", depth_vis)



    else:
        print("Error: No image data received")

    # Exit if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
out.release()
cv2.destroyAllWindows()
print("Video saved as airsim_output.avi")
