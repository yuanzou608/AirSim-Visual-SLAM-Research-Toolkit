#!/usr/bin/env python3
from pathlib import Path
import shutil

SOURCE_ROOT = Path(
    "/home/yuan/SLAM/Hier-SLAM/Hier-SLAM/experiments/Airsim_no_semantic"
)

TARGET_ROOT = Path(
    "/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_no_semantic"
)


def main():
    if not SOURCE_ROOT.is_dir():
        raise FileNotFoundError(f"Source root does not exist: {SOURCE_ROOT}")

    if not TARGET_ROOT.is_dir():
        raise FileNotFoundError(f"Target root does not exist: {TARGET_ROOT}")

    missing_source = []
    copied = []
    already_exists = []

    # 以目标目录中的一级数据集文件夹为准。
    # 例如 target/building25fps -> 查找 source/building25fps_5 和 _6。
    dataset_dirs = sorted(
        p for p in TARGET_ROOT.iterdir()
        if p.is_dir()
    )

    for dataset_dir in dataset_dirs:
        dataset_name = dataset_dir.name
        frames_dir = dataset_dir / "500frames"

        for trial_id in ("5", "6"):
            src = SOURCE_ROOT / f"{dataset_name}_{trial_id}"
            dst = frames_dir / trial_id

            # 源实验目录缺失：记录，最后统一报告
            if not src.is_dir():
                missing_source.append(src)
                print(f"[MISSING] {src}")
                continue

            # 目标已存在时不覆盖，避免误删已有实验结果
            if dst.exists():
                already_exists.append(dst)
                print(f"[SKIP] Target already exists: {dst}")
                continue

            # 只有确认源目录存在、目标不存在时才创建 500frames
            frames_dir.mkdir(parents=True, exist_ok=True)

            print(f"[COPY] {src} -> {dst}")
            shutil.copytree(src, dst)
            copied.append((src, dst))

    print("\n" + "=" * 90)
    print("Copy summary")
    print("=" * 90)

    print(f"\nSuccessfully copied: {len(copied)}")
    for src, dst in copied:
        print(
            f"  - {src.name} -> "
            f"{dst.relative_to(TARGET_ROOT)}"
        )

    print(f"\nMissing source folders: {len(missing_source)}")
    if missing_source:
        for src in missing_source:
            print(f"  - {src.name}")
    else:
        print("  None")

    print(f"\nExisting targets skipped: {len(already_exists)}")
    if already_exists:
        for dst in already_exists:
            print(f"  - {dst.relative_to(TARGET_ROOT)}")
    else:
        print("  None")


if __name__ == "__main__":
    main()
