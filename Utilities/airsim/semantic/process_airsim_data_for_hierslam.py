import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from tqdm import tqdm
import shutil
from scipy.spatial.transform import Rotation as R
from glob import glob
'''
This file process airsim data for hier-slam, the output data is under /home/yuan/airsim/data/replica_format, you should copy
and paste these files like replica dataset in your destination directory
'''

def convert_airsim_to_replica_format(ROOT=None, dataset=None):
    if ROOT is None:
        rgb_dir = "/home/yuan/dataset/my_data/square25fps/rgb"
        depth_dir = "/home/yuan/dataset/my_data/square25fps/depth"
        semantic_dir = "/home/yuan/dataset/my_data/square25fps/semantic"

        out_rgb = "/home/yuan/dataset/my_data/square25fps/replica_format/rgb"
        out_depth = "/home/yuan/dataset/my_data/square25fps/replica_format/depth"
        out_sem = "/home/yuan/dataset/my_data/square25fps/replica_format/vis_sem_class"
    else:
        rgb_dir = os.path.join(ROOT, dataset, "rgb")
        depth_dir = os.path.join(ROOT, dataset, "depth")
        semantic_dir = os.path.join(ROOT, dataset, "semantic")

        out_rgb = os.path.join(ROOT, dataset, "replica_format","rgb")
        out_depth = os.path.join(ROOT, dataset, "replica_format","depth")
        out_sem = os.path.join(ROOT, dataset, "replica_format","semantic")

    os.makedirs(out_rgb, exist_ok=True)
    os.makedirs(out_depth, exist_ok=True)
    os.makedirs(out_sem, exist_ok=True)

    timestamps = sorted([f for f in os.listdir(rgb_dir) if f.endswith(".png")])

    for i, fname in enumerate(tqdm(timestamps, desc="Converting to replica format rgb, depth and semantic")):
        base = f"{i:06d}"
        rgb_path = os.path.join(rgb_dir, fname)
        depth_path = os.path.join(depth_dir, fname)
        sem_path = os.path.join(semantic_dir, fname)

        # Convert PNG to JPG for RGB
        rgb_img = Image.open(rgb_path).convert("RGB")  # Ensure 3 channels
        rgb_img.save(os.path.join(out_rgb, f"frame{base}.jpg"), "JPEG", quality=95)

        # Copy depth and semantic without format change
        shutil.copy(depth_path, os.path.join(out_depth, f"depth{base}.png"))
        shutil.copy(sem_path, os.path.join(out_sem, f"vis_sem_class_{i}.png"))

    print("✅ RGB converted to JPG and files renamed.")

def copy_to_results(ROOT, dataset):
    rgb_dir = os.path.join(ROOT, dataset, "replica_format", "rgb")
    depth_dir = os.path.join(ROOT, dataset, "replica_format", "depth")

    out_dir = os.path.join(ROOT, dataset, "results")

    os.makedirs(out_dir, exist_ok=True)

    # 复制 RGB
    rgb_imgs = sorted(glob(os.path.join(rgb_dir, "*")))
    for img in rgb_imgs:
        shutil.copy(img, out_dir)

    # 复制 Depth
    depth_imgs = sorted(glob(os.path.join(depth_dir, "*")))
    for img in depth_imgs:
        shutil.copy(img, out_dir)

    print(f"Copied {len(rgb_imgs)} RGB images and {len(depth_imgs)} depth images to {out_dir}")


def find_all_unique_color():
    semantic_dir = "/home/yuan/Downloads/gt_semantic"
    unique_colors = set()

    # Go through all .png files in the folder
    for id, fname in enumerate(sorted(os.listdir(semantic_dir))):
        if not fname.endswith(".png"):
            continue

        if id % 100 == 0:
            print(f"Processing {id}/{len(os.listdir(semantic_dir))}")

        img_path = os.path.join(semantic_dir, fname)
        img = cv2.imread(img_path)
        if img is None:
            print(f"Warning: Could not read {fname}")
            continue

        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Flatten to list of RGB tuples
        pixels = img_rgb.reshape(-1, 3)
        for color in np.unique(pixels, axis=0):
            unique_colors.add(tuple(color))

    print(f"\nFound {len(unique_colors)} unique colors across all semantic images:")
    for color in sorted(unique_colors):
        print(color)

def color_to_label(color_dict):
    for color, label in color_dict.items():
        # Color to verify
        rgb = color

        # Create a 100x100 image filled with this color
        img = np.ones((100, 100, 3), dtype=np.uint8)
        img[:] = rgb

        plt.imshow(img)
        plt.title(f"{label}: {rgb}")
        plt.axis('off')
        plt.show()

def convert_to_grayscale_semantic(color_to_id, ROOT="/home/yuan/dataset/my_data", dataset="road25fps"):
    semantic_dir = f"/{ROOT}/{dataset}/semantic"
    output_dir = f"/{ROOT}/{dataset}/replica_format/semantic_class"
    os.makedirs(output_dir, exist_ok=True)

    # === Get and sort all semantic image files ===
    image_files = sorted([
        f for f in os.listdir(semantic_dir)
        if f.lower().endswith(('.png'))
    ])

    # === Process with sequential naming ===
    for idx, fname in enumerate(tqdm(image_files, desc="Converting semantic images")):
        input_path = os.path.join(semantic_dir, fname)
        output_name = f"semantic_class_{idx}.png"
        output_path = os.path.join(output_dir, output_name)

        # Load image
        rgb_img = np.array(Image.open(input_path))

        # Initialize grayscale label map
        label_map = np.zeros((rgb_img.shape[0], rgb_img.shape[1]), dtype=np.uint8)

        # Map RGB color to class ID
        for color, class_id in color_to_id.items():
            mask = np.all(rgb_img == color, axis=-1)
            label_map[mask] = class_id

        # Save as grayscale image
        Image.fromarray(label_map).save(output_path)

def convert_gt_trajectory():
    input_file = "/home/yuan/dataset/my_data/square25fps/groundtruth.txt"  # TUM format
    output_file = "/home/yuan/dataset/my_data/square25fps/traj.txt"  # Hier-SLAM format

    with open(input_file, 'r') as f_in, open(output_file, 'w') as f_out:
        for line in f_in:
            if line.startswith("#") or len(line.strip()) == 0:
                continue  # skip comments and empty lines

            parts = list(map(float, line.strip().split()))
            if len(parts) != 8:
                continue  # invalid line

            tx, ty, tz = parts[1:4]
            qx, qy, qz, qw = parts[4:]

            # Convert quaternion to rotation matrix
            rot = R.from_quat([qx, qy, qz, qw]).as_matrix()

            # Form 4x4 matrix
            pose = np.eye(4)
            pose[:3, :3] = rot
            pose[:3, 3] = [tx, ty, tz]

            # Flatten to row-major
            pose_flat = pose.flatten()
            pose_str = " ".join(f"{v:.18e}" for v in pose_flat)
            f_out.write(pose_str + "\n")

    print(f"done! gt trajectory saved to {output_file}")

def visualize_one_semantic_image(image):
    # Load grayscale label image (values are class IDs)
    label = np.array(Image.open(image))
    print(label.shape)
    plt.imshow(label)
    plt.axis('off')

    # Scale values for visibility: e.g., class 1 → 10, class 6 → 60
    enhanced = label * 10

    # Display with matplotlib's default colormap or 'gray'
    plt.imshow(enhanced, cmap='nipy_spectral')  # or 'tab10', 'viridis', etc.
    plt.colorbar()
    plt.title(f"Semantic Label Visualization (scaled x10)")
    plt.axis('off')
    plt.show()

import os
import shutil

def copy_to_folder(ROOT, dataset):
    dataset_root = os.path.join(ROOT, dataset)

    # ---------- 1. 复制 info_semantic.json ----------
    src_info = os.path.join("info_semantic.json")
    dst_info = os.path.join(dataset_root, "info_semantic.json")

    if os.path.exists(src_info):
        print(f"[INFO] Copying {src_info} → {dst_info}")
        shutil.copy2(src_info, dst_info)
    else:
        print(f"[WARN] info_semantic.json not found: {src_info}")

    # ---------- 2. 移动 semantic_class 文件夹 ----------
    src_semantic_class = os.path.join(dataset_root, "replica_format", "semantic_class")
    dst_semantic_class = os.path.join(dataset_root, "semantic_class")

    if os.path.exists(src_semantic_class):
        # 如果目标已存在，先删除
        if os.path.exists(dst_semantic_class):
            print(f"[INFO] Removing existing {dst_semantic_class}")
            shutil.rmtree(dst_semantic_class)

        print(f"[INFO] Moving {src_semantic_class} → {dst_semantic_class}")
        shutil.move(src_semantic_class, dst_semantic_class)
    else:
        print(f"[WARN] semantic_class folder not found: {src_semantic_class}")


if __name__ == "__main__":
    # convert airsim data to candidate replicace format
    # convert_airsim_to_replica_format()

    # extract all visual color and its label
    # find_all_unique_color()

    # # define color corresponding label
    # color_dict = {
    #     (0, 0, 0): 'background',
    #     (81, 13, 36): 'power',
    #     (89, 121, 72): 'car',
    #     (112, 105, 191): 'bush',
    #     (115, 176, 195): 'sign',
    #     (153, 108, 6): 'tree',
    #     (206, 190, 59): 'furniture'
    # }
    # color_dict = {
    # (0, 0, 0): 'background',
    # (71, 146, 227): '1',
    # (167, 140, 147): '2',
    # (157, 23, 236): '3',
    # (29, 26, 199): '4',
    # (215, 4, 215): '5',
    # (75, 50, 243): '6',
    # (121, 67, 28): '7',
    # (161, 171, 27): '8',
    # (184, 145, 182): '9',
    # (54, 72, 205): '10',
    # (146, 52, 70): '11',
    # (158, 114, 88): '12',
    # (89, 121, 72): '13',
    # (68, 218, 116):'14',
    # (153, 108, 6): '15',
    # (53, 118, 126): '16',
    # (55, 181, 57): '17',
    # (206, 190, 59): '18',
    # (226, 149, 143): '19',
    # (43, 47, 206): '20',
    # (241, 77, 149): '21',
    # (98, 55, 74): '22',
    # (242, 107, 146): '23',
    # (40, 63, 99): '24',
    # (3, 177, 32): '25',
    # (245, 22, 110): '26',
    # (151, 126, 171): '27',
    # (185, 243, 231): '28',
    # (67, 17, 35): '29',
    # (115, 176, 195): '30',
    # (156, 198, 23): '31',
    # (181, 213, 93): '32',
    # (222, 153, 109): '33',
    # (24, 175, 120): '34',
    # (134, 57, 119): '35',
    # (170, 179, 42): '36',
    # (253, 41, 164): '37'
    # }

    # color_to_label(color_dict)

    # # convert to grayscale for hierslam
    # color_to_id = {
    #     (0, 0, 0): 0,  # background
    #     (81, 13, 36): 6,  # power
    #     (89, 121, 72): 3,  # car
    #     (112, 105, 191): 2,  # bush
    #     (115, 176, 195): 7,  # sign
    #     (153, 108, 6): 1,  # tree
    #     (206, 190, 59): 5  # furniture
    # }
    color_to_id = {
    (0, 0, 0): 0,
        (0, 53, 65): 1,
        (1, 222, 192): 2,
        (3, 177, 32): 3,
        (8, 234, 216): 4,
        (11, 236, 9): 5,
        (15, 241, 102): 6,
        (19, 132, 69): 7,
        (24, 175, 120): 8,
        (25, 62, 174): 9,
        (29, 26, 199): 10,
        (37, 128, 125): 11,
        (40, 63, 99): 12,
        (43, 47, 206): 13,
        (52, 187, 148): 14,
        (53, 118, 126): 15,
        (54, 72, 205): 16,
        (55, 181, 57): 17,
        (67, 17, 35): 18,
        (68, 218, 116): 19,
        (71, 146, 227): 20,
        (75, 50, 243): 21,
        (85, 152, 34): 22,
        (89, 121, 72): 23,
        (90, 162, 242): 24,
        (93, 14, 71): 25,
        (94, 253, 175): 26,
        (98, 55, 74): 27,
        (99, 242, 104): 28,
        (101, 109, 181): 29,
        (103, 252, 157): 30,
        (109, 206, 24): 31,
        (112, 105, 191): 32,
        (115, 176, 195): 33,
        (119, 230, 85): 34,
        (121, 67, 28): 35,
        (124, 21, 123): 36,
        (125, 75, 48): 37,
        (126, 129, 238): 38,
        (134, 57, 119): 39,
        (146, 52, 70): 40,
        (151, 126, 171): 41,
        (153, 108, 6): 42,
        (156, 198, 23): 43,
        (157, 23, 236): 44,
        (158, 114, 88): 45,
        (161, 171, 27): 46,
        (164, 194, 17): 47,
        (167, 140, 147): 48,
        (170, 179, 42): 49,
        (173, 69, 31): 50,
        (181, 213, 93): 51,
        (182, 251, 87): 52,
        (184, 145, 182): 53,
        (185, 243, 231): 54,
        (189, 135, 188): 55,
        (194, 39, 7): 56,
        (195, 237, 132): 57,
        (196, 30, 8): 58,
        (199, 29, 1): 59,
        (202, 97, 155): 60,
        (205, 120, 161): 61,
        (206, 190, 59): 62,
        (207, 229, 90): 63,
        (211, 80, 208): 64,
        (212, 51, 60): 65,
        (215, 4, 215): 66,
        (216, 78, 75): 67,
        (218, 124, 115): 68,
        (222, 153, 109): 69,
        (226, 149, 143): 70,
        (234, 20, 250): 71,
        (241, 77, 149): 72,
        (242, 107, 146): 73,
        (245, 22, 110): 74,
        (247, 200, 111): 75,
        (253, 41, 164): 76
    }

    # # convert color semantic to gray semantic
    # convert_to_grayscale_semantic(color_to_id)

    # # convert tum to hierslam format
    # convert_gt_trajectory()

    # visualize, in order to better visualize, times 10 for each pixel
    # image = '/home/yuan/airsim/data/replica_format/semantic_class/semantic_class_0.png'
    # visualize_one_semantic_image(image)

#===================================batch file============================================
    ROOT = "/home/yuan/data2tb/dataset/my_data"
    dataset_list = [
        # "testdata",
        "road25fps",
        "cross_building_medium_medium",
        "houses_medium_medium",
        "roundabout_square25fps",
        "road2_low_low",
        "roundabout2_low_medium",
        "road2_low_high",
        "pool_high_medium",
        "pool_high_low",
        "houses_high_medium",
        "pool_medium_low",
        "road2_medium_medium",
        "road2_high_high",
        "pool_medium_high",
        "pool_medium_medium",
        "houses_low_medium",
        "road2_high_low",
        "roundabout2_low_high",
        "road2_medium_high",
        "cross_building_low_medium",
        "houses_low_high",
        "cross_building_high_medium",
        "roundabout2_high_medium",
        "cross_building_high_low",
        "houses_medium_low",
        "cross_building_medium_high",
        "houses_high_low",
        "houses_low_low",
        "road2_low_medium",
        "cross_building_low_high",
        "cross_building_low_low",
        "houses_high_high",
        "roundabout2_medium_low",
        "cross_building_medium_low",
        "roundabout2_medium_high",
        "pool_high_high",
        "cross_building_high_high",
        "roundabout2_high_high",
        "roundabout2_high_low",
        "roundabout25fps",
        "pool_low_high",
        "houses_medium_high",
        "building25fps",
        "roundabout2_low_low",
        "road2_high_medium",
        "road2_medium_low",
        "pool_low_low",
        "pool_low_medium",
    ]
    for dataset in dataset_list:
        print(f"Processing {dataset}...")
        # convert_airsim_to_replica_format(ROOT, dataset)

        # copy_to_results(ROOT, dataset)
        convert_to_grayscale_semantic(color_to_id, ROOT, dataset)
        copy_to_folder(ROOT, dataset)


