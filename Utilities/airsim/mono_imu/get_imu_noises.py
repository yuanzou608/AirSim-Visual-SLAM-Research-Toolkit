import pandas as pd
# Load the uploaded IMU data file
imu_file_path = "imu_data_no_move.csv"

# Read the IMU data
imu_df = pd.read_csv(imu_file_path)

# Compute IMU noise parameters

# Noise (standard deviation of angular velocity and linear acceleration)
IMU_NoiseGyro = imu_df[['angular_velocity_x', 'angular_velocity_y', 'angular_velocity_z']].std()
IMU_NoiseAcc = imu_df[['linear_acceleration_x', 'linear_acceleration_y', 'linear_acceleration_z']].std()

# Random Walk Noise (approximated as the standard deviation of the first-order difference)
IMU_GyroWalk = imu_df[['angular_velocity_x', 'angular_velocity_y', 'angular_velocity_z']].diff().std()
IMU_AccWalk = imu_df[['linear_acceleration_x', 'linear_acceleration_y', 'linear_acceleration_z']].diff().std()


# Combine the computed IMU noise parameters into ORB_SLAM3 format

imu_config = {
    "IMU.NoiseGyro": IMU_NoiseGyro.mean(),  # Average noise for gyroscope
    "IMU.NoiseAcc": IMU_NoiseAcc.mean(),    # Average noise for accelerometer
    "IMU.GyroWalk": IMU_GyroWalk.mean(),    # Average random walk noise for gyroscope
    "IMU.AccWalk": IMU_AccWalk.mean()       # Average random walk noise for accelerometer
}

# Convert to DataFrame for better visibility
imu_config_df = pd.DataFrame(imu_config, index=["IMU Settings"])

# Display the final ORB_SLAM3 IMU noise settings
print(imu_config_df)


