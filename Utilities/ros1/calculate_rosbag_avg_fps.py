import os
import subprocess
import pandas as pd

# Manually define bag file path since user handles ROS setup
bag_dir = ""
bag_file = None

# Look for the first .bag file in /workspace
if os.path.exists(bag_dir):
    for file in os.listdir(bag_dir):
        if file.endswith(".bag"):
            bag_file = os.path.join(bag_dir, file)
            break

# Parse rosbag info output
summary = []
if bag_file:
    try:
        result = subprocess.run(["rosbag", "info", bag_file], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        current_topic = None
        message_count = None
        duration = None
        for line in lines:
            if line.strip().startswith("topic:"):
                current_topic = line.split(":")[1].strip()
            elif line.strip().startswith("messages:"):
                message_count = int(line.split(":")[1].strip())
            elif line.strip().startswith("duration:"):
                duration_str = line.split(":")[1].strip().split(" ")[0]
                try:
                    duration = float(duration_str)
                except ValueError:
                    duration = None
            elif line.strip().startswith("type:") and current_topic and message_count is not None and duration:
                freq = message_count / duration if duration > 0 else 0
                summary.append({
                    "Topic": current_topic,
                    "Message Count": message_count,
                    "Duration (s)": round(duration, 3),
                    "Avg Frequency (Hz)": round(freq, 2)
                })
                current_topic = None
                message_count = None
                duration = None
    except Exception as e:
        summary = [{"Error": str(e)}]
else:
    summary = [{"Error": "No .bag file found in /workspace"}]

import pandas as pd
df = pd.DataFrame(summary)
print(df.to_string(index=False))  # 更好格式的输出
