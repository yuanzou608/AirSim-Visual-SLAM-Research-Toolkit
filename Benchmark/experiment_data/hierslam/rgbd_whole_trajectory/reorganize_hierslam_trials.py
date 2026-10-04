#!/usr/bin/env python3
from pathlib import Path
import argparse
import re
import shutil

ROOT = Path("/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_no_semantic")


def reorganize_dataset(dataset_dir: Path, dry_run: bool = False) -> None:
    """
    For one dataset folder, e.g.:
        building25fps/
            building25fps_1/
            building25fps_2/
            building25fps_3/

    Create:
        building25fps/complete/

    Then move/rename to:
        building25fps/complete/1/
        building25fps/complete/2/
        building25fps/complete/3/
    """
    complete_dir = dataset_dir / "complete"

    # Only match folders whose names are:
    # <current dataset folder name>_1 / _2 / _3
    pattern = re.compile(rf"^{re.escape(dataset_dir.name)}_([123])$")

    matched = []

    for child in dataset_dir.iterdir():
        if not child.is_dir():
            continue

        match = pattern.match(child.name)
        if match:
            trial_id = match.group(1)
            matched.append((child, complete_dir / trial_id))

    if not matched:
        print(f"[SKIP] {dataset_dir.name}: no *_1, *_2, *_3 folders found")
        return

    print(f"\n[DATASET] {dataset_dir.name}")

    if dry_run:
        print(f"  [DRY-RUN] mkdir -p {complete_dir}")
    else:
        complete_dir.mkdir(exist_ok=True)

    for src, dst in sorted(matched, key=lambda x: x[0].name):
        if dst.exists():
            print(f"  [SKIP] target already exists: {dst}")
            continue

        print(f"  {src.name}  ->  complete/{dst.name}")

        if not dry_run:
            shutil.move(str(src), str(dst))


def main():
    parser = argparse.ArgumentParser(
        description="Move <dataset>_1/_2/_3 into <dataset>/complete/1,2,3."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned changes; do not modify files."
    )
    args = parser.parse_args()

    if not ROOT.exists():
        raise FileNotFoundError(f"Root folder does not exist: {ROOT}")

    dataset_dirs = sorted(
        p for p in ROOT.iterdir()
        if p.is_dir()
    )

    print(f"Root: {ROOT}")
    print(f"Found {len(dataset_dirs)} top-level folders.")

    for dataset_dir in dataset_dirs:
        reorganize_dataset(dataset_dir, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
