import numpy as np
from scipy.spatial.transform import Rotation as R

# Camera quaternion
camera_quat = [0.0, 0.0, 0.7071, 0.7071]  # [x, y, z, w]
camera_rot = R.from_quat(camera_quat).as_matrix()

# IMU quaternion
imu_quat = [0.0, 0.0, 0.0, 1.0]  # [x, y, z, w]
imu_rot = R.from_quat(imu_quat).as_matrix()

print("Camera Rotation Matrix:\n", camera_rot)
print("IMU Rotation Matrix:\n", imu_rot)

camera_position = np.array([0.4599999785423279, 0.0, -0.14649587869644165])

# Construct 4x4 transformation matrix
T_camera = np.eye(4)
T_camera[:3, :3] = camera_rot
T_camera[:3, 3] = camera_position

T_imu = np.eye(4)
T_imu[:3, :3] = imu_rot

# Transformation from camera to IMU
T_camera_to_imu = np.linalg.inv(T_camera) @ T_imu

print("Transformation from Camera to IMU:\n", T_camera_to_imu)
