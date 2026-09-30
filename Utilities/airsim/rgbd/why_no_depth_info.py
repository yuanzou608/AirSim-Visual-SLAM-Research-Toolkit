# import airsim
import cv2
import numpy as np
import matplotlib.pyplot as plt
# the reason if we do not set far distance as small distance, all small values will be calculate
# near to 0
# Connect to AirSim
# client = airsim.MultirotorClient(ip="127.0.0.1")  # Change IP if needed
# client.confirmConnection()

# Capture an image from the front_left_custom camera
# requests = [airsim.ImageRequest("front_left_custom",
#                                 airsim.ImageType.DepthPlanar,
#                                 pixels_as_float=True,
#                                 compress=False)]

# Get image response
# responses = client.simGetImages(requests)
responses = '4348.794000.png'

def depth_without_limit_max():
    if responses and responses[0].image_data_float:
        # Convert depth image to NumPy array
        depth_data = np.array(responses[0].image_data_float, dtype=np.float32)

        # Reshape to correct dimensions
        depth_image = depth_data.reshape(responses[0].height, responses[0].width)
        # depth_image[depth_image > 100] = 50  # Optional: Clamp max depth

        # To avoid extreme values dominating, clamp (clip) using, e.g., 5th/95th percentiles
        low_val = np.percentile(depth_image, 5)  # 5% depth
        high_val = np.percentile(depth_image, 95)  # 95% depth
        depth_clamped = np.clip(depth_image, low_val, high_val)

        # Normalize depth values to 8-bit for visualization
        depth_normalized = cv2.normalize(depth_clamped, None, 0, 255, cv2.NORM_MINMAX)
        depth_8bit = depth_normalized.astype(np.uint8)

        # Convert to BGR for imshow
        depth_vis = cv2.cvtColor(depth_8bit, cv2.COLOR_GRAY2BGR)

        return depth_vis

        # # Show the image
        # cv2.imshow("Depth Image", depth_vis)
        # cv2.waitKey(0)  # Wait until a key is pressed
        # cv2.destroyAllWindows()
        #
        # # Save the image
        # cv2.imwrite("/home/yuan/airsim/scripts/airsim/rgbd/depth_image_without_clamp.png", depth_vis)
        # print("Image saved as depth_image.png")

    else:
        print("Error: No image data received")
def depth_with_limit_max():
    if responses and responses[0].image_data_float:
        # Convert depth image to NumPy array
        depth_data = np.array(responses[0].image_data_float, dtype=np.float32)

        # Reshape to correct dimensions
        depth_image = depth_data.reshape(responses[0].height, responses[0].width)
        depth_image[depth_image > 50] = 50  # Optional: Clamp max depth

        # To avoid extreme values dominating, clamp (clip) using, e.g., 5th/95th percentiles
        low_val = np.percentile(depth_image, 5)  # 5% depth
        high_val = np.percentile(depth_image, 95)  # 95% depth
        depth_clamped = np.clip(depth_image, low_val, high_val)

        # Normalize depth values to 8-bit for visualization
        depth_normalized = cv2.normalize(depth_clamped, None, 0, 255, cv2.NORM_MINMAX)
        depth_8bit = depth_normalized.astype(np.uint8)

        # Convert to BGR for imshow
        depth_vis = cv2.cvtColor(depth_8bit, cv2.COLOR_GRAY2BGR)

        # # Show the image
        # cv2.imshow("Depth Image", depth_vis)
        # cv2.waitKey(0)  # Wait until a key is pressed
        # cv2.destroyAllWindows()
        #
        # # Save the image
        # cv2.imwrite("/home/yuan/airsim/scripts/airsim/rgbd/depth_image_without_clamp.png", depth_vis)
        # print("Image saved as depth_image.png")
        return depth_vis

    else:
        print("Error: No image data received")

def show_images(image1, image2, title1=None, title2=None):
    fig, axs = plt.subplots(1, 2, figsize=(12, 8))
    axs[0].imshow(image1)
    axs[0].axis('off')
    axs[1].imshow(image2)
    axs[1].axis('off')
    if title1 and title2 is not None:
        axs[0].set_title(title1)
        axs[1].set_title(title2)
    plt.savefig('no_depth_vs_depth_image.png', dpi=300)
    plt.show()


def show_histogram(depth_data1, depth_data2, title1="No Depth Limit", title2="With Depth Limit"):
    plt.figure(figsize=(12, 6))

    # Plot Histogram for first depth image
    plt.subplot(1, 2, 1)
    plt.hist(depth_data1.ravel(), bins=50, color='blue', alpha=0.7)
    plt.title(f"Histogram: {title1}")
    plt.xlabel("Depth Value")
    plt.ylabel("Pixel Count")

    # Plot Histogram for second depth image
    plt.subplot(1, 2, 2)
    plt.hist(depth_data2.ravel(), bins=50, color='red', alpha=0.7)
    plt.title(f"Histogram: {title2}")
    plt.xlabel("Depth Value")
    plt.ylabel("Pixel Count")
    plt.savefig('no_depth_vs_depth_histogram.png', dpi=300)

    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    no_depth_image = depth_without_limit_max()
    depth_image = depth_with_limit_max()
    show_images(no_depth_image, depth_image, title1="No Depth Image", title2="Depth Image")
    show_histogram(no_depth_image, depth_image, title1="No Depth Limit", title2="With Depth Limit")

