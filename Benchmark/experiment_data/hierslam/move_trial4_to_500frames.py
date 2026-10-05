#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path("/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_no_semantic")


def main():
    if not ROOT.exists():
        raise FileNotFoundError(f"Root folder does not exist: {ROOT}")

    missing_4 = []
    already_moved = []
    moved = []
    skipped_conflict = []

    # 只处理 ROOT 下的一级文件夹；csv 等文件自动忽略
    dataset_dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())

    for dataset_dir in dataset_dirs:
        src = dataset_dir / "4"
        dst_parent = dataset_dir / "500frames"
        dst = dst_parent / "4"

        # 如果已经存在 dataset/500frames/4，认为已经处理过
        if not src.exists() and dst.is_dir():
            already_moved.append(dataset_dir.name)
            print(f"[ALREADY] {dataset_dir.name}: 500frames/4 already exists")
            continue

        # 当前 dataset 下没有 4 文件夹
        if not src.is_dir():
            missing_4.append(dataset_dir.name)
            print(f"[MISSING] {dataset_dir.name}: no folder '4'")
            continue

        # 防止覆盖已经存在的目标
        if dst.exists():
            skipped_conflict.append(dataset_dir.name)
            print(
                f"[CONFLICT] {dataset_dir.name}: both '4' and '500frames/4' exist; "
                "skipped to avoid overwriting"
            )
            continue

        dst_parent.mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(dataset_dir.name)
        print(f"[MOVED] {dataset_dir.name}/4 -> {dataset_dir.name}/500frames/4")

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    print(f"\nMoved: {len(moved)}")
    for name in moved:
        print(f"  - {name}")

    print(f"\nMissing folder '4': {len(missing_4)}")
    if missing_4:
        for name in missing_4:
            print(f"  - {name}")
    else:
        print("  None")

    print(f"\nAlready moved: {len(already_moved)}")
    for name in already_moved:
        print(f"  - {name}")

    print(f"\nConflicts skipped: {len(skipped_conflict)}")
    for name in skipped_conflict:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
