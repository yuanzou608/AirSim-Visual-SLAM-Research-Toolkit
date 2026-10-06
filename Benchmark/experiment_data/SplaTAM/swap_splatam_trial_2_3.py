#!/usr/bin/env python3
from pathlib import Path
import argparse

ROOT = Path("/home/yuan/data2tb/experiments/SplaTAM/experiments/airsim")
TEMP_NAME = "__swap_tmp_2_3__"


def main():
    parser = argparse.ArgumentParser(
        description="Swap folder names '2' and '3' inside every dataset directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show planned swaps; do not rename anything."
    )
    args = parser.parse_args()

    if not ROOT.is_dir():
        raise FileNotFoundError(f"Root folder does not exist: {ROOT}")

    swapped = []
    missing = []
    conflicts = []

    dataset_dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())

    for dataset_dir in dataset_dirs:
        folder2 = dataset_dir / "2"
        folder3 = dataset_dir / "3"
        temp = dataset_dir / TEMP_NAME

        missing_parts = []
        if not folder2.is_dir():
            missing_parts.append("2")
        if not folder3.is_dir():
            missing_parts.append("3")

        if missing_parts:
            missing.append((dataset_dir.name, missing_parts))
            print(
                f"[MISSING] {dataset_dir.name}: "
                f"missing folder(s) {', '.join(missing_parts)}"
            )
            continue

        if temp.exists():
            conflicts.append(dataset_dir.name)
            print(
                f"[CONFLICT] {dataset_dir.name}: temporary folder "
                f"'{TEMP_NAME}' already exists; skipped"
            )
            continue

        if args.dry_run:
            print(
                f"[DRY-RUN] {dataset_dir.name}: "
                f"2 -> {TEMP_NAME}, 3 -> 2, {TEMP_NAME} -> 3"
            )
        else:
            folder2.rename(temp)
            folder3.rename(folder2)
            temp.rename(folder3)
            print(f"[SWAPPED] {dataset_dir.name}: 2 <-> 3")

        swapped.append(dataset_dir.name)

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    label = "Would swap" if args.dry_run else "Swapped"
    print(f"\n{label}: {len(swapped)}")
    for name in swapped:
        print(f"  - {name}")

    print(f"\nMissing required folders: {len(missing)}")
    if missing:
        for name, parts in missing:
            print(f"  - {name}: missing {', '.join(parts)}")
    else:
        print("  None")

    print(f"\nConflicts skipped: {len(conflicts)}")
    if conflicts:
        for name in conflicts:
            print(f"  - {name}")
    else:
        print("  None")


if __name__ == "__main__":
    main()
