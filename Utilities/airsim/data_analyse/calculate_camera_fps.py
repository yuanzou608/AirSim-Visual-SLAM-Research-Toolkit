import airsim
import time

camera_name = "front_left_custom"
# camera_name = "0"
# 1. Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()

# 2. Warm-up 
client.simGetImage(camera_name, airsim.ImageType.Scene)

# 3. Start timing
N = 100   # number of images to fetch
start_time = time.time()

for _ in range(N):
    img = client.simGetImage(camera_name, airsim.ImageType.Scene)

end_time = time.time()

# 4. Calculate FPS
elapsed = end_time - start_time
fps = N / elapsed

print(f"Effective Camera FPS: {fps:.2f}")



