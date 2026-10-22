#!/usr/bin/env python3
"""Copy each SplaTAM RGB-D dataset's run 2 into matching archive datasets.

Default: preview only.
Run:     python copy_splatam_rgbd_run2.py --copy

Existing destination 2 directories are skipped (never overwritten).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SOURCE_ROOT = Path("/home/yuan/SLAM/SplaTAM/SplaTAM/experiments/airsim/rgbd")
TARGET_ROOT = Path("/home/yuan/data2tb/experiments/SplaTAM/experiments/airsim")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy run-2 folders from SplaTAM RGB-D experiments into corresponding archived datasets."
    )
    parser.add_argument(
        "--copy", action="store_true", help="Perform the copy; otherwise preview only."
    )
    args = parser.parse_args()

    if not SOURCE_ROOT.is_dir():
        print(f"ERROR: Source root not found: {SOURCE_ROOT}", file=sys.stderr)
        return 1
    if not TARGET_ROOT.is_dir():
        print(f"ERROR: Destination root not found: {TARGET_ROOT}", file=sys.stderr)
        return 1

    copied = 0
    previewed = 0
    skipped_missing_src = 0
    skipped_missing_target = 0
    skipped_existing = 0
    errors = 0

    print("MODE:", "COPY" if args.copy else "PREVIEW (no files modified)")
    print("Source:", SOURCE_ROOT)
    print("Target:", TARGET_ROOT)
    print()

    datasets = sorted(
        p for p in SOURCE_ROOT.iterdir() if p.is_dir() and not p.is_symlink()
    )
    for dataset in datasets:
        source_run = dataset / "2"
        target_dataset = TARGET_ROOT / dataset.name
        target_run = target_dataset / "2"

        if not source_run.is_dir() or source_run.is_symlink():
            print(f"[SKIP: NO SOURCE 2] {dataset.name}")
            skipped_missing_src += 1
            continue
        if not target_dataset.is_dir() or target_dataset.is_symlink():
            print(f"[SKIP: NO TARGET DATASET] {dataset.name}")
            skipped_missing_target += 1
            continue
        if target_run.exists() or target_run.is_symlink():
            print(f"[SKIP: TARGET 2 EXISTS] {dataset.name}: {target_run}")
            skipped_existing += 1
            continue

        if not args.copy:
            print(f"[WOULD COPY] {source_run} -> {target_run}")
            previewed += 1
        else:
            try:
                # Exclusive directory creation: no merging or overwriting.
                # Preserve symbolic links rather than dereferencing them.
                shutil.copytree(source_run, target_run, symlinks=True)
                print(f"[COPIED] {source_run} -> {target_run}")
                copied += 1
            except (OSError, shutil.Error) as exc:
                print(f"[ERROR] {dataset.name}: {exc}", file=sys.stderr)
                print(f"        Check possibly incomplete destination: {target_run}", file=sys.stderr)
                errors += 1

    print("\nSummary:")
    print(f"  Dataset folders found:   {len(datasets)}")
    print(f"  {'Copied' if args.copy else 'Ready to copy'}: {copied if args.copy else previewed}")
    print(f"  Missing source 2:        {skipped_missing_src}")
    print(f"  Missing target dataset:  {skipped_missing_target}")
    print(f"  Existing target 2:       {skipped_existing}")
    print(f"  Errors:                  {errors}")
    if not args.copy:
        print("\nRun with --copy to actually copy the folders.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
