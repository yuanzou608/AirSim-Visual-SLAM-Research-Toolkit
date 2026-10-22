#!/usr/bin/env python3
"""Delete run folder '2' directly inside each AirSim dataset directory.

By default, only print matching directories. Pass --delete to actually remove them.
"""

import argparse
import shutil
from pathlib import Path

ROOT = Path('/home/yuan/data2tb/experiments/SplaTAM/experiments/airsim')


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete only direct '2' subfolders in SplaTAM AirSim datasets")
    parser.add_argument('--delete', action='store_true', help='Actually remove the matching folders (default: preview only)')
    args = parser.parse_args()

    if not ROOT.is_dir() or ROOT.is_symlink():
        parser.error(f'Root folder not found or is a symlink: {ROOT}')

    targets = sorted(
        dataset / '2'
        for dataset in ROOT.iterdir()
        if dataset.is_dir() and not dataset.is_symlink()
        and (dataset / '2').is_dir() and not (dataset / '2').is_symlink()
    )

    if not targets:
        print("No direct subfolders named '2' found. Nothing to do.")
        return

    print(f"Found {len(targets)} dataset folders containing a direct '2' subfolder:")
    for target in targets:
        print(f"  {target}")

    if not args.delete:
        print("\nPreview only. To permanently delete these folders, rerun with --delete.")
        return

    failures = 0
    for target in targets:
        try:
            shutil.rmtree(target)
            print(f'Deleted: {target}')
        except OSError as exc:
            failures += 1
            print(f'FAILED: {target} ({exc})')
    print(f'\nFinished: {len(targets) - failures} deleted, {failures} failed.')


if __name__ == '__main__':
    main()
