import airsim
import time
import numpy as np

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)  # Enable API control
client.armDisarm(True)  # Arm drone

# Takeoff
print("Taking off...")
client.takeoffAsync().join()

# Ensure IMU gets motion data
print("Performing IMU initialization maneuvers...")

# Move in a square pattern to generate IMU data
motion_duration = 0.5  # Duration for each move
speed = 2.0  # Speed in m/s
imu_rate_hz       = 200.0  # IMU frequency
image_rate_hz     = 20.0   # Image frequency
capture_duration  = 45.0   # Seconds to capture data
# Rotate to introduce orientation changes
yaw_rate = 0  # Degrees per second
rotation_duration = 2  # Time for rotation

iters = 3 # how many iteration for each action
for i in range(iters):
# Move forward
    client.moveByVelocityAsync(speed, 0, 0, motion_duration).join()
# Move backward
    client.moveByVelocityAsync(-speed, 0, 0, motion_duration).join()
# Move left
    client.moveByVelocityAsync(0, -speed, 0, motion_duration).join()
# Move right
    client.moveByVelocityAsync(0, speed, 0, motion_duration).join()
# Move up
    client.moveByVelocityAsync(0, 0, speed, motion_duration).join()
# Move down
    client.moveByVelocityAsync(0, 0, -speed, motion_duration).join()

    print("Rotating for IMU initialization...")
    client.rotateByYawRateAsync(yaw_rate, rotation_duration).join()

    # Hover for stability
    print("Hovering to stabilize IMU...")
    client.hoverAsync().join()
    time.sleep(2)
    print(f"iter {i} completed")
# client.moveByVelocityAsync(0.1, -0.0, -0.1, capture_duration * (int(image_rate_hz//6 + 1))).join() # we will "compress" the images into a rosbag
# Land
print("Landing...")
client.landAsync().join()

# Disable motors and release API control
client.armDisarm(False)
client.enableApiControl(False)

print("IMU initialization complete. Ready for ORB_SLAM3.")
