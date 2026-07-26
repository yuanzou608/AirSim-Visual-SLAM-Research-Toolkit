import airsim
from collections import Counter
import re

client = airsim.MultirotorClient()  # or CarClient, etc.
client.confirmConnection()

# Assign IDs
UNKNOWN_CLASS_ID = 0  # make it black if needed
label_class_map = set()
object_names = client.simListSceneObjects()
for obj_name in object_names:
    if re.match(r"Banister", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Banister"))

    if re.match(r"Basketball", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Basketball"))

    if re.match(r"Bed", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Bed"))

    if re.match(r"Bench", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Bench"))

    if re.match(r"bin", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "bin"))

    if re.match(r"Birch", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Birch"))

    if re.match(r"Book", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Book"))

    if re.match(r"Bookcase", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Bookcase"))

    if re.match(r"BRPlayer", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "BRPlayer"))

    if re.match(r"Car", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Car"))

    if re.match(r"Chair", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Chair"))

    if re.match(r"Chimney", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Chimney"))

    if re.match(r"Cladding", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Cladding"))

    if re.match(r"Curtain", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Curtain"))

    if re.match(r"Drain", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Drain"))

    if re.match(r"Drinks", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Drinks"))

    if re.match(r"Driveway", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Driveway"))

    if re.match(r"extractor", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "extractor"))

    if re.match(r"fan", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "fan"))

    if re.match(r"Fence", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Fence"))

    if re.match(r"Fir(_|\d|$)", obj_name): # match only fir, not fireplace
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Fir"))

    if re.match(r"Flat_Roof", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Flat_Roof"))

    if re.match(r"Floor", obj_name) or re.match(r"Flor", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Floor"))

    if re.match(r"Garden", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Garden"))

    if re.match(r"Hedge", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Hedge"))

    if re.match(r"House", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "House"))

    if re.match(r"Inner", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Inner"))

    if re.match(r"Leaves", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Leaves"))

    if re.match(r"Oak", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Oak"))

    if re.match(r"Outdoor_Steps", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Outdoor_Steps"))

    if re.match(r"Outer", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Outer"))

    if re.match(r"Porch", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Porch"))

    if re.match(r"Road", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Road"))

    if re.match(r"Rock", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Rock"))

    if re.match(r"Roof", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Roof"))

    if re.match(r"Shelf", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Shelf"))

    if re.match(r"Shutters", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Shutters"))

    if re.match(r"Stop_Sign", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Stop_Sign"))

    if re.match(r"Street_Sign", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Street_Sign"))

    if re.match(r"Swimming_Pool", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Swimming_Pool"))

    if re.match(r"Tree", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Tree"))

    if re.match(r"Veranda", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Veranda"))

    if re.match(r"Wall", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Wall"))

    if re.match(r"Garage", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Garage"))

    if re.match(r"Small_House", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Small_House"))

    if re.match(r"Landscape_0", obj_name):
        # print(obj_name)
        label = 255
        client.simSetSegmentationObjectID(obj_name, label, False)
        label_class_map.add((label, "Landscape_0"))

    # if re.match(r"coffee", obj_name):
    #     print(obj_name)
    #     label = 0
    #     client.simSetSegmentationObjectID(obj_name, label, False)
    #     label_class_map.add((label, "Landscape_0"))


# Save mapping
with open("label_class_map.txt", "w") as f:
    for label_id, prefix in sorted(label_class_map):
        f.write(f"{label_id} {prefix}\n")