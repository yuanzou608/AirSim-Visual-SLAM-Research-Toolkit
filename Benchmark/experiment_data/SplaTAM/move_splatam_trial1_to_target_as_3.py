#!/usr/bin/env python3
from pathlib import Path
import argparse
import shutil

SOURCE_ROOT = Path("/home/yuan/SLAM/SplaTAM/experiments/airsim")
TARGET_ROOT = Path("/home/yuan/data2tb/experiments/SplaTAM/experiments/airsim")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Move each dataset's source experiment folder '1' to the corresponding "
            "target dataset folder and rename it to '3'."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show planned operations; do not move anything."
    )
    args = parser.parse_args()

    if not SOURCE_ROOT.is_dir():
        raise FileNotFoundError(f"Source root does not exist: {SOURCE_ROOT}")

    if not TARGET_ROOT.is_dir():
        raise FileNotFoundError(f"Target root does not exist: {TARGET_ROOT}")

    moved = []
    missing_trial_1 = []
    conflicts = []
    created_target_dirs = []

    dataset_dirs = sorted(p for p in SOURCE_ROOT.iterdir() if p.is_dir())

    for source_dataset_dir in dataset_dirs:
        dataset_name = source_dataset_dir.name

        source_trial = source_dataset_dir / "1"
        target_dataset_dir = TARGET_ROOT / dataset_name
        target_trial = target_dataset_dir / "3"

        if not source_trial.is_dir():
            missing_trial_1.append(dataset_name)
            print(f"[MISSING] {dataset_name}: source folder '1' not found")
            continue

        if target_trial.exists():
            conflicts.append(dataset_name)
            print(f"[CONFLICT] {target_trial} already exists; skipped")
            continue

        if not target_dataset_dir.exists():
            created_target_dirs.append(dataset_name)
            if args.dry_run:
                print(f"[DRY-RUN] mkdir -p {target_dataset_dir}")
            else:
                target_dataset_dir.mkdir(parents=True, exist_ok=True)

        if args.dry_run:
            print(f"[DRY-RUN] MOVE {source_trial} -> {target_trial}")
        else:
            shutil.move(str(source_trial), str(target_trial))
            print(f"[MOVED] {source_trial} -> {target_trial}")

        moved.append(dataset_name)

    print("\n" + "=" * 90)
    print("Summary")
    print("=" * 90)

    label = "Would move" if args.dry_run else "Moved"
    print(f"\n{label}: {len(moved)}")
    for name in moved:
        print(f"  - {name}: 1 -> 3")

    print(f"\nMissing source folder '1': {len(missing_trial_1)}")
    if missing_trial_1:
        for name in missing_trial_1:
            print(f"  - {name}")
    else:
        print("  None")

    print(f"\nExisting target '3' conflicts: {len(conflicts)}")
    if conflicts:
        for name in conflicts:
            print(f"  - {name}")
    else:
        print("  None")

    created_label = "Target dataset folders that would be created" if args.dry_run else "Target dataset folders created"
    print(f"\n{created_label}: {len(created_target_dirs)}")
    if created_target_dirs:
        for name in created_target_dirs:
            print(f"  - {name}")
    else:
        print("  None")


if __name__ == "__main__":
    main()
