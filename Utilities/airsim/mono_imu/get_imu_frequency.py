import rosbag

# Path to your ROS bag file
bag_file = "/home/yuan/airsim/rosbags/mono_imu/orb_slam3_ros1.bag"
imu_topic = "/imu"

timestamps = []

# Open ROS bag and extract IMU timestamps
with rosbag.Bag(bag_file, "r") as bag:
    for topic, msg, t in bag.read_messages(topics=[imu_topic]):
        timestamps.append(t.to_sec())  # Convert ROS time to seconds

# Compute IMU Frequency
if len(timestamps) > 1:
    total_time = timestamps[-1] - timestamps[0]  # Total duration
    imu_frequency = len(timestamps) / total_time if total_time > 0 else 0
    print(f"Computed IMU Frequency: {imu_frequency:.2f} Hz")
else:
    print("Not enough IMU messages to compute frequency.")
