from pathlib import Path
import shutil


# =========================
# Paths
# =========================

DATA_ROOT = Path("/home/yuan/data2tb/dataset/my_data")

SPLATAM_ROOT = Path(
    "/home/yuan/data2tb/experiments/SplaTAM/experiments/airsim"
)

RUN_IDS = ["1", "2", "3"]


def main():
    copied_count = 0
    skipped_count = 0

    # 遍历所有 dataset folder
    for dataset_dir in sorted(DATA_ROOT.iterdir()):

        if not dataset_dir.is_dir():
            continue

        dataset_name = dataset_dir.name

        source_gt = dataset_dir / "groundtruth.txt"

        # -------------------------
        # 检查 source groundtruth
        # -------------------------
        if not source_gt.exists():
            print(
                f"[SKIP] {dataset_name}: "
                f"groundtruth.txt does not exist"
            )
            skipped_count += 1
            continue

        # 对应的 SplaTAM dataset folder
        target_dataset_dir = SPLATAM_ROOT / dataset_name

        # -------------------------
        # 如果整个实验 folder 不存在
        # -------------------------
        if not target_dataset_dir.exists():
            print(
                f"[SKIP] {dataset_name}: "
                f"SplaTAM experiment folder does not exist"
            )
            skipped_count += 1
            continue

        print(f"\n=== {dataset_name} ===")

        # -------------------------
        # 遍历 run 1 / 2 / 3
        # -------------------------
        for run_id in RUN_IDS:

            run_dir = target_dataset_dir / run_id

            # 实验失败可能没有这个 run
            if not run_dir.exists():
                print(
                    f"  [SKIP] run {run_id}: "
                    f"run folder does not exist"
                )
                skipped_count += 1
                continue

            poses_dir = run_dir / "poses"

            # poses 不存在也不创建
            if not poses_dir.exists():
                print(
                    f"  [SKIP] run {run_id}: "
                    f"poses folder does not exist"
                )
                skipped_count += 1
                continue

            target_gt = poses_dir / "groundtruth.txt"

            # -------------------------
            # Copy
            # -------------------------
            shutil.copy2(source_gt, target_gt)

            print(
                f"  [COPY] run {run_id}: "
                f"{target_gt}"
            )

            copied_count += 1

    # =========================
    # Summary
    # =========================

    print("\n" + "=" * 60)
    print("Finished")
    print(f"Copied : {copied_count}")
    print(f"Skipped: {skipped_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()