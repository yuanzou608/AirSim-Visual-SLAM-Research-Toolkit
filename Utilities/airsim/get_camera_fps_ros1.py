import rosbag

# Path to your ROS bag file
bag_file = "/home/yuan/airsim/rosbags/mono_imu/orb_slam3_ros1.bag"
topic = "/camera/image_raw"  # Replace with the actual topic

timestamps = []

# Open ROS bag and extract timestamps
with rosbag.Bag(bag_file, "r") as bag:
    for topic, msg, t in bag.read_messages(topics=[topic]):
        timestamps.append(t.to_sec())

# Compute FPS
if len(timestamps) > 1:
    total_time = timestamps[-1] - timestamps[0]
    fps = len(timestamps) / total_time if total_time > 0 else 0
    print(f"Computed FPS: {fps:.2f}")
else:
    print("Not enough frames to compute FPS.")
