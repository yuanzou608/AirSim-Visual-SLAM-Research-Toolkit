import rosbag2_py

# Path to your ROS 2 bag file (Ensure it points to the correct `.db3` folder)
bag_file = "/home/performer/dev_ws/rosbags"  # Adjust path accordingly
topic = "/airsim_node/SimpleFlight/front_left_custom/DepthPlanar"  # Adjust your topic

def compute_fps(bag_file, topic):
    storage_options = rosbag2_py.StorageOptions(uri=bag_file, storage_id="sqlite3")
    converter_options = rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr")

    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)

    timestamps = []

    while reader.has_next():
        (topic_name, data, timestamp) = reader.read_next()
        if topic_name == topic:
            timestamps.append(timestamp * 1e-9)  # Convert nanoseconds to seconds

    if len(timestamps) > 1:
        total_time = timestamps[-1] - timestamps[0]
        fps = len(timestamps) / total_time if total_time > 0 else 0
        print(f"Computed FPS: {fps:.2f}")
    else:
        print("Not enough frames to compute FPS.")

compute_fps(bag_file, topic)
