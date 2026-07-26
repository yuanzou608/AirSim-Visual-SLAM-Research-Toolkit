import os


def rename_groundtruth():
    root = "/home/yuan/data2tb/dataset/my_data"

    for folder in os.listdir(root):
        folder_path = os.path.join(root, folder)
        if not os.path.isdir(folder_path):
            continue

        old_path = os.path.join(folder_path, "groundtruth.txt")
        new_path = os.path.join(folder_path, "groundtruth_origin.txt")

        if os.path.exists(old_path):
            print(f"Renaming: {old_path} -> {new_path}")
            os.rename(old_path, new_path)

    print("Done!")


def regenerate_groundtruth():
    ROOT = "/home/yuan/data2tb/dataset/my_data"

    for folder in sorted(os.listdir(ROOT)):
        folder_path = os.path.join(ROOT, folder)
        if not os.path.isdir(folder_path):
            continue

        assoc_path = os.path.join(folder_path, "associations.txt")
        gt_origin_path = os.path.join(folder_path, "groundtruth_origin.txt")
        gt_out_path = os.path.join(folder_path, "groundtruth.txt")

        # 只处理同时有 associations 和 groundtruth_origin 的 dataset
        if not (os.path.exists(assoc_path) and os.path.exists(gt_origin_path)):
            print(f"[SKIP] {folder_path}: missing associations.txt or groundtruth_origin.txt")
            continue

        print(f"[PROCESS] {folder_path}")

        # 1. 读取 associations.txt 中所有 timestamp（第一列）
        assoc_timestamps = set()
        with open(assoc_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) == 0:
                    continue
                ts = parts[0]
                assoc_timestamps.add(ts)

        # 2. 过滤 groundtruth_origin.txt
        kept_lines = []
        removed_count = 0
        total_count = 0

        with open(gt_origin_path, "r") as f:
            for line in f:
                stripped = line.strip()
                # 注释行或空行，原样保留
                if not stripped or stripped.startswith("#"):
                    kept_lines.append(line)
                    continue

                parts = stripped.split()
                if len(parts) == 0:
                    continue

                ts = parts[0]
                total_count += 1

                if ts in assoc_timestamps:
                    kept_lines.append(line)
                else:
                    removed_count += 1

        # 3. 写回 groundtruth.txt
        with open(gt_out_path, "w") as f:
            f.writelines(kept_lines)

        print(f"    total pose lines: {total_count}, removed: {removed_count}, kept: {total_count - removed_count}")
        print(f"    -> wrote {gt_out_path}")

    print("All done.")

def remove_tum_timestamp():
    ROOT = "/home/yuan/data2tb/dataset/my_data"

    for folder in sorted(os.listdir(ROOT)):
        folder_path = os.path.join(ROOT, folder)
        if not os.path.isdir(folder_path):
            continue

        gt_path = os.path.join(folder_path, "groundtruth.txt")
        out_path = os.path.join(folder_path, "groundtruth_no_ts.txt")

        if not os.path.exists(gt_path):
            print(f"[SKIP] {folder}: no groundtruth.txt")
            continue

        print(f"[PROCESS] {folder}")

        lines_out = []
        with open(gt_path, "r") as f:
            lines = f.readlines()

        # 1. 去掉第一行（一般是 "# timestamp tx ty ..."）
        data_lines = lines[1:] if len(lines) > 0 else []

        # 2. 去掉每一行的第1列 timestamp
        for line in data_lines:
            stripped = line.strip()
            if not stripped:
                continue

            parts = stripped.split()
            if len(parts) <= 1:
                continue

            # 去掉 timestamp，保留后面的 tx ty tz qx qy qz qw
            new_line = " ".join(parts[1:])
            lines_out.append(new_line + "\n")

        # 3. 保存 groundtruth_no_ts.txt
        with open(out_path, "w") as f:
            f.writelines(lines_out)

        print(f"    -> wrote {out_path}")

    print("Done.")


if __name__ == "__main__":
    # rename_groundtruth()
    # rename_groundtruth()
    remove_tum_timestamp()