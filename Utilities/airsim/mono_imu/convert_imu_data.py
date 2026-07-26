import pandas as pd

# Load the IMU data
file_path = "imu_data.csv"  # Update this with the correct file path
imu_data = pd.read_csv(file_path)

# Reverse the sign of linear_acceleration_z
imu_data["linear_acceleration_z"] = -imu_data["linear_acceleration_z"]

# Swap linear_acceleration_x and linear_acceleration_z
imu_data[["linear_acceleration_x", "linear_acceleration_z"]] = imu_data[["linear_acceleration_z", "linear_acceleration_x"]]

# Save the modified data
modified_file_path = "modified_imu_data.csv"  # Update the path as needed
imu_data.to_csv(modified_file_path, index=False)

print(f"Modified IMU data saved to: {modified_file_path}")
