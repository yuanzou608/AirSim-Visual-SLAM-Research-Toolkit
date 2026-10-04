import numpy as np
import os

def rotation_matrix_to_quaternion(R):
    """
    输入: 3x3 旋转矩阵
    输出: (qx, qy, qz, qw)  四元数
    """
    R = np.array(R, dtype=float)
    assert R.shape == (3, 3)

    trace = np.trace(R)
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2, 1] - R[1, 2]) * s
        qy = (R[0, 2] - R[2, 0]) * s
        qz = (R[1, 0] - R[0, 1]) * s
    else:
        if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
            qw = (R[2, 1] - R[1, 2]) / s
            qx = 0.25 * s
            qy = (R[0, 1] + R[1, 0]) / s
            qz = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
            qw = (R[0, 2] - R[2, 0]) / s
            qx = (R[0, 1] + R[1, 0]) / s
            qy = 0.25 * s
            qz = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
            qw = (R[1, 0] - R[0, 1]) / s
            qx = (R[0, 2] + R[2, 0]) / s
            qy = (R[1, 2] + R[2, 1]) / s
            qz = 0.25 * s

    return qx, qy, qz, qw


def convert_camera_poses_to_tum(
    input_path="camera_poses.txt",
    output_path="trajectory_tum.txt",
    start_ts=1.0,
    delta=0.1,
):
    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        idx = 0
        for line in fin:
            line = line.strip()
            if not line:
                continue  # 跳过空行

            parts = line.split()
            if len(parts) != 16:
                raise ValueError(f"第 {idx} 行不是 16 个数: {len(parts)} 个")

            vals = list(map(float, parts))
            T = np.array(vals, dtype=float).reshape(4, 4)

            R = T[:3, :3]
            t = T[:3, 3]

            qx, qy, qz, qw = rotation_matrix_to_quaternion(R)

            ts = start_ts + idx * delta

            # TUM 格式: timestamp tx ty tz qx qy qz qw
            fout.write(
                f"{ts:.6f} "
                f"{t[0]:.6f} {t[1]:.6f} {t[2]:.6f} "
                f"{qx:.6f} {qy:.6f} {qz:.6f} {qw:.6f}\n"
            )

            idx += 1

    print(f" {idx} poses  {input_path} -> {output_path}")


if __name__ == "__main__":
    dataset_list = [
        "building25fps",
        "cross_building_high_high",
        "cross_building_high_low",
        "cross_building_high_medium",
        "cross_building_low_high",
        "cross_building_low_low",
        "cross_building_low_medium",
        "cross_building_medium_high",
        "cross_building_medium_low",
        "cross_building_medium_medium",
        "houses_high_high",
        "houses_high_low",
        "houses_high_medium",
        "houses_low_high",
        "houses_low_low",
        "houses_low_medium",
        "houses_medium_high",
        "houses_medium_low",
        "houses_medium_medium",
        "pool_high_high",
        "pool_high_low",
        "pool_high_medium",
        "pool_low_high",
        "pool_low_low",
        "pool_low_medium",
        "pool_medium_high",
        "pool_medium_low",
        "pool_medium_medium",
        "road25fps",
        "road2_high_high",
        "road2_high_low",
        "road2_high_medium",
        "road2_low_high",
        "road2_low_low",
        "road2_low_medium",
        "road2_medium_high",
        "road2_medium_low",
        "road2_medium_medium",
        "roundabout25fps",
        "roundabout2_high_high",
        "roundabout2_high_low",
        "roundabout2_high_medium",
        "roundabout2_low_high",
        "roundabout2_low_low",
        "roundabout2_low_medium",
        "roundabout2_medium_high",
        "roundabout2_medium_low",
        "roundabout_square25fps"
    ]

    root = "/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_no_semantic"

    missing_records = []
    failed_conversions = []

    # 逐个 trial 处理 estimate.txt 和 groundtruth.txt。
    # 某个文件不存在时不报错退出，而是记录下来，最后统一报告。
    for dataset in dataset_list:
        for i in ["1", "2", "3"]:
            trial_dir = os.path.join(root, dataset, "complete", str(i))

            for filename in ["estimate.txt", "groundtruth.txt"]:
                source = os.path.join(trial_dir, filename)
                target_name = filename.replace(".txt", "_tum.txt")
                target = os.path.join(trial_dir, target_name)

                if not os.path.isfile(source):
                    missing_records.append((trial_dir, filename))
                    print(f"[MISSING] {source}")
                    continue

                try:
                    convert_camera_poses_to_tum(
                        input_path=source,
                        output_path=target,
                        start_ts=0.0,
                        delta=1.0,
                    )
                except Exception as e:
                    # 即使某个已有文件内容损坏，也不中断整个批处理。
                    failed_conversions.append((source, str(e)))
                    print(f"[ERROR] {source}: {e}")

    print("\n" + "=" * 80)
    print("Conversion summary")
    print("=" * 80)

    if missing_records:
        print(f"\nMissing input files: {len(missing_records)}")
        for trial_dir, filename in missing_records:
            rel_dir = os.path.relpath(trial_dir, root)
            print(f"  - {rel_dir}: missing {filename}")
    else:
        print("\nMissing input files: 0")

    if failed_conversions:
        print(f"\nConversion errors: {len(failed_conversions)}")
        for source, error in failed_conversions:
            rel_source = os.path.relpath(source, root)
            print(f"  - {rel_source}: {error}")
    else:
        print("\nConversion errors: 0")
