import airsim
from collections import Counter

client = airsim.MultirotorClient()  # or CarClient, etc.
client.confirmConnection()

# Get all object names in the scene
object_names = client.simListSceneObjects()
print("Found", len(object_names), "objects")
with open("raw_segmentation.txt", "w") as f:
    for name in object_names:
        f.write(f"{name}\n")

# Count label prefixes
prefix_counter = Counter()
for name in object_names:
    prefix = name.split("_")[0]
    prefix_counter[prefix] += 1

sorted_prefixes = sorted(prefix_counter.items(), key=lambda x: -x[1])
with open("count_segmentation.txt", "w") as f:
    for object in sorted_prefixes:
        f.write(f"{object[0]}:{object[1]}\n")


semantic_groups = {
    1: ["Tree", "Fir", "Pine", "Oak"],                     # 树木
    2: ["Car", "Car_Porch", "Car_Prefab"],          # 汽车
    3: ["Building", "House", "Structure", "house", "wall"],          # 建筑
    4: ["Road", "Street", "Asphalt"],               # 道路
    5: ["Fence", "Wall", "Barrier"],                # 围栏
    6: ["Stairs", "Steps", "Outdoor_Steps"],        # 台阶
    7: ["Ground", "Grass", "Dirt"],                 # 地面
    8: ["Landscape"],                               # 景观
}

for label_id, keywords in semantic_groups.items():
    for obj_name in object_names:
        for keyword in keywords:
            if keyword.lower() in obj_name.lower():
                client.simSetSegmentationObjectID(obj_name, label_id, False)

with open("segmentation.txt", "w") as f:
    for label_id, keywords in semantic_groups.items():
        for keyword in keywords:
            f.write(f"{label_id} {keyword}\n")

# skip_keywords = [
#     "pointlight", "camera", "game", "hud", "actor", "default",
#     "light", "volume", "manager", "capture", "external", "decal",
#     "sky", "weather", "postprocess", "cue", "ambience", "audio"
# ]
#
# # skip background
# for name in object_names:
#     prefix = name.split("_")[0].lower()
#     if prefix in skip_keywords:
#         client.simSetSegmentationObjectID(name, 255, False)

#
# # Auto-class ID assignment
# semantic_label_map = {}
# semantic_id = 1
# MIN_OBJECTS = 2
#
# for prefix, count in sorted_prefixes:
#     if count < MIN_OBJECTS:
#         continue
#     if prefix.lower() in [
#         "pointlight", "camera", "game", "hud", "actor", "default", "light", "volume", "manager", "capture", "external", "decal", "sky", "weather", "postprocess"
#     ]:
#         continue
#     semantic_label_map[prefix] = semantic_id
#     semantic_id += 1
#
# # Assign IDs
# UNKNOWN_CLASS_ID = 0  # make it black if needed
# used_labels = set()
# for obj_name in object_names:
#     prefix = obj_name.split("_")[0]
#     label_id = semantic_label_map.get(prefix, UNKNOWN_CLASS_ID)
#     client.simSetSegmentationObjectID(obj_name, label_id, False)
#     used_labels.add((label_id, prefix))
#
# # Save mapping
# with open("segmentation.txt", "w") as f:
#     for label_id, prefix in sorted(used_labels):
#         f.write(f"{label_id} {prefix}\n")
#
# print(f"✅ Assigned {len(semantic_label_map)} semantic classes.")
# print("📄 Saved segmentation.txt")
#
#
