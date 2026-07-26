from collections import Counter
import re
import airsim

client = airsim.MultirotorClient()  # or CarClient, etc.
client.confirmConnection()

object_names = client.simListSceneObjects()

prefix_counter = Counter()
for name in object_names:
    prefix = name.split("_")[0]
    prefix_counter[prefix] += 1

# 查看前缀统计结果
for prefix, count in sorted(prefix_counter.items(), key=lambda x: -x[1]):
    print(f"{prefix}: {count}")

