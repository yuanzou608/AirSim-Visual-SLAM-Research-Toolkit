import airsim
import numpy as np

client = airsim.MultirotorClient()
client.confirmConnection()

# Get camera pose
camera_name = "0"
camera_info = client.simGetCameraInfo(camera_name)
camera_pose = camera_info.pose

# Get IMU pose (position in AirSim may not be provided explicitly)
vehicle_name = ""  # Specify vehicle name if applicable
imu_data = client.getImuData("imu", vehicle_name)

print("Camera Position:", camera_pose.position)
print("Camera Orientation:", camera_pose.orientation)
print("IMU Orientation:", imu_data.orientation)
