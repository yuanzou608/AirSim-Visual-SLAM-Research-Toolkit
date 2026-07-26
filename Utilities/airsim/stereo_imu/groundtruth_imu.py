import airsim
import csv
import os
import time

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# File paths
kinematics_file = "groundtruth.csv"
imu_file = "imu_data.csv"

# Flags for writing headers
write_kin_header = not os.path.exists(kinematics_file)
write_imu_header = not os.path.exists(imu_file)

# Loop to collect 100 rows
for i in range(1000):
    # Get data
    kinematics = client.simGetGroundTruthKinematics()
    imu_response = client.getImuData()
    # Ground truth data (with orientation added)
    kinematics_data = {
        'linear_velocity_x': kinematics.linear_velocity.x_val,
        'linear_velocity_y': kinematics.linear_velocity.y_val,
        'linear_velocity_z': kinematics.linear_velocity.z_val,
        'linear_acceleration_x': kinematics.linear_acceleration.x_val,
        'linear_acceleration_y': kinematics.linear_acceleration.y_val,
        'linear_acceleration_z': kinematics.linear_acceleration.z_val,
        'angular_velocity_x': kinematics.angular_velocity.x_val,
        'angular_velocity_y': kinematics.angular_velocity.y_val,
        'angular_velocity_z': kinematics.angular_velocity.z_val,
        'position_x': kinematics.position.x_val,
        'position_y': kinematics.position.y_val,
        'position_z': kinematics.position.z_val,
        'orientation_w': kinematics.orientation.w_val,
        'orientation_x': kinematics.orientation.x_val,
        'orientation_y': kinematics.orientation.y_val,
        'orientation_z': kinematics.orientation.z_val,
    }

    # IMU data
    imu_data = {
        'linear_acceleration_x': imu_response.linear_acceleration.x_val,
        'linear_acceleration_y': imu_response.linear_acceleration.y_val,
        'linear_acceleration_z': imu_response.linear_acceleration.z_val,
        'angular_velocity_x': imu_response.angular_velocity.x_val,
        'angular_velocity_y': imu_response.angular_velocity.y_val,
        'angular_velocity_z': imu_response.angular_velocity.z_val,
        'orientation_w': imu_response.orientation.w_val,
        'orientation_x': imu_response.orientation.x_val,
        'orientation_y': imu_response.orientation.y_val,
        'orientation_z': imu_response.orientation.z_val,
        'time_stamp': imu_response.time_stamp,
    }

    # Write kinematics data
    with open(kinematics_file, mode='a', newline='') as kf:
        writer = csv.DictWriter(kf, fieldnames=kinematics_data.keys())
        if write_kin_header:
            writer.writeheader()
            write_kin_header = False
        writer.writerow(kinematics_data)

    # Write IMU data
    with open(imu_file, mode='a', newline='') as imuf:
        writer = csv.DictWriter(imuf, fieldnames=imu_data.keys())
        if write_imu_header:
            writer.writeheader()
            write_imu_header = False
        writer.writerow(imu_data)


    # Optional: add a small delay (adjust as needed)
    time.sleep(0.05)  # 50ms

print('kinematics: ', kinematics)
print('imu_data: ', imu_data)
print("✅ Finished recording 100 rows of kinematics and IMU data.")
