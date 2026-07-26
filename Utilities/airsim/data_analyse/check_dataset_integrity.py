import os
import numpy as np

def load_list(txt_file):
    timestamps = []
    files = []
    if not os.path.exists(txt_file):
        return np.array([]), []
    with open(txt_file, 'r') as f:
        for line in f:
            if line.strip() == "" or line.startswith("#"):
                continue
            parts = line.split()
            ts, fp = parts[0], parts[1]
            timestamps.append(float(ts))
            files.append(os.path.basename(fp))
    return np.array(timestamps), files

def load_associations(assoc_file):
    rgb_files = []
    depth_files = []
    if not os.path.exists(assoc_file):
        return [], []
    with open(assoc_file, 'r') as f:
        for line in f:
            if line.strip() == "" or line.startswith("#"):
                continue
            parts = line.split()
            rgb_files.append(os.path.basename(parts[1]))
            depth_files.append(os.path.basename(parts[3]))
    return rgb_files, depth_files

def get_png_files(folder):
    if not os.path.exists(folder):
        return set()
    return {f for f in os.listdir(folder) if f.lower().endswith(".png")}

def nearest_match(base_ts, query_ts, threshold=0.03):
    if len(query_ts) == 0:
        return -1
    diffs = np.abs(query_ts - base_ts)
    idx = np.argmin(diffs)
    return idx if diffs[idx] <= threshold else -1


def main(dataset_path):
    has_issue = False  # only print if needed

    rgb_txt   = os.path.join(dataset_path, "rgb.txt")
    depth_txt = os.path.join(dataset_path, "depth.txt")
    assoc_txt = os.path.join(dataset_path, "associations.txt")

    rgb_folder   = os.path.join(dataset_path, "rgb")
    depth_folder = os.path.join(dataset_path, "depth")

    rgb_ts, rgb_files_list = load_list(rgb_txt)
    depth_ts, depth_files_list = load_list(depth_txt)
    assoc_rgb, assoc_depth = load_associations(assoc_txt)

    rgb_folder_files   = get_png_files(rgb_folder)
    depth_folder_files = get_png_files(depth_folder)

    # =============== STRICT RGB ===============
    rgb_extra_in_folder = rgb_folder_files - set(rgb_files_list)
    rgb_missing_in_folder = set(rgb_files_list) - rgb_folder_files
    assoc_missing_rgb = set(assoc_rgb) - set(rgb_files_list)

    # =============== STRICT DEPTH ===============
    depth_extra_in_folder = depth_folder_files - set(depth_files_list)
    depth_missing_in_folder = set(depth_files_list) - depth_folder_files
    assoc_missing_depth = set(assoc_depth) - set(depth_files_list)

    # =============== TIMESTAMP MATCHING ===============
    MAX_DIFF = 0.00
    matched_depth_by_ts = set()
    missing_rgb_ts = []

    for i, ts in enumerate(rgb_ts):
        j = nearest_match(ts, depth_ts, MAX_DIFF)
        if j >= 0:
            matched_depth_by_ts.add(depth_files_list[j])
        else:
            missing_rgb_ts.append(rgb_files_list[i])

    matched_set = matched_depth_by_ts
    assoc_set = set(assoc_depth)

    extra_by_timestamp = matched_set - assoc_set
    missing_by_timestamp = assoc_set - matched_set

    # =============== PRINT ONLY IF ISSUES ===============

    # If everything is perfect → do not print anything
    if not (
        rgb_extra_in_folder or rgb_missing_in_folder or assoc_missing_rgb or
        depth_extra_in_folder or depth_missing_in_folder or assoc_missing_depth or
        extra_by_timestamp or missing_by_timestamp or missing_rgb_ts
    ):
        return  # silent success

    # If reach here → print issues only
    print(f"\n=== Issues found in dataset: {dataset_path} ===")

    # RGB issues
    if rgb_extra_in_folder:
        print("Extra RGB images in folder:", sorted(rgb_extra_in_folder))
    if rgb_missing_in_folder:
        print("rgb.txt references missing RGB images:", sorted(rgb_missing_in_folder))
    if assoc_missing_rgb:
        print("associations.txt refers to RGB not in rgb.txt:", sorted(assoc_missing_rgb))

    # Depth issues
    if depth_extra_in_folder:
        print("Extra depth images in folder:", sorted(depth_extra_in_folder))
    if depth_missing_in_folder:
        print("depth.txt references missing depth images:", sorted(depth_missing_in_folder))
    if assoc_missing_depth:
        print("associations.txt refers to depth not in depth.txt:", sorted(assoc_missing_depth))

    # Timestamp issues
    if extra_by_timestamp:
        print("Timestamp-matchable depth not in associations.txt:", sorted(extra_by_timestamp))
    if missing_by_timestamp:
        print("Associations depth cannot be timestamp-matched:", sorted(missing_by_timestamp))
    if missing_rgb_ts:
        print("RGB frames with no timestamp-matchable depth:", missing_rgb_ts[:20],
              f"... total {len(missing_rgb_ts)}" if len(missing_rgb_ts) > 20 else "")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python check_rgb_depth_associations.py <dataset_folder>")
        exit(1)
    main(sys.argv[1])
