import airsim
import csv

client = airsim.VehicleClient()
client.confirmConnection()

# Get IMU pose (vehicle body frame)
imu_pose = client.simGetVehiclePose().orientation
imu_position = client.simGetVehiclePose().position
imu_data = client.getImuData()

# Get Camera pose
camera_pose = client.simGetCameraInfo("front_center_custom").pose.orientation
camera_position = client.simGetCameraInfo("front_center_custom").pose.position

# Get Ground Truth Data
ground_truth_data = client.simGetGroundTruthKinematics()

print('imu data: ', imu_data)
print('\nground truth data: ', ground_truth_data)

print("\nIMU Position:", imu_position)
print("\nIMU Orientation:", imu_pose)
print("\nCamera Position:", camera_position)
print("\nCamera Orientation:", camera_pose)

csv_data = [
    ["Parameter", "X", "Y", "Z", "W"],
    ["IMU Position", imu_position.x_val, imu_position.y_val, imu_position.z_val, ""],
    ["IMU Orientation", imu_pose.x_val, imu_pose.y_val, imu_pose.z_val, imu_pose.w_val],
    ["IMU Linear Acceleration", imu_data.linear_acceleration.x_val, imu_data.linear_acceleration.y_val, imu_data.linear_acceleration.z_val, ""],
    ["IMU Angular Velocity", imu_data.angular_velocity.x_val, imu_data.angular_velocity.y_val, imu_data.angular_velocity.z_val, ""],
    ["Camera Position", camera_position.x_val, camera_position.y_val, camera_position.z_val, ""],
    ["Camera Orientation", camera_pose.x_val, camera_pose.y_val, camera_pose.z_val, camera_pose.w_val],
    ["Ground Truth Position", ground_truth_data.position.x_val, ground_truth_data.position.y_val, ground_truth_data.position.z_val, ""],
    ["Ground Truth Orientation", ground_truth_data.orientation.x_val, ground_truth_data.orientation.y_val, ground_truth_data.orientation.z_val, ground_truth_data.orientation.w_val],
    ["Ground Truth Velocity", ground_truth_data.linear_velocity.x_val, ground_truth_data.linear_velocity.y_val, ground_truth_data.linear_velocity.z_val, ""],  # ✅ Fixed this line
    ["Ground Truth Acceleration", ground_truth_data.linear_acceleration.x_val, ground_truth_data.linear_acceleration.y_val, ground_truth_data.linear_acceleration.z_val, ""],
    ["Ground Truth Angular Velocity", ground_truth_data.angular_velocity.x_val, ground_truth_data.angular_velocity.y_val, ground_truth_data.angular_velocity.z_val, ""],
]

csv_filename = "imu_camera_data.csv"
# Save to CSV
with open(csv_filename, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerows(csv_data)

print(f"Data saved to {csv_filename}")
