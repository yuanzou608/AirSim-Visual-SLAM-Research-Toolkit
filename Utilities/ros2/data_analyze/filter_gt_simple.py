#!/usr/bin/env python3
# Minimal: keep only rows in groundtruth.txt whose timestamp exists in the RGB folder.
# Usage:
#   python3 filter_gt_simple.py /path/to/groundtruth.txt /path/to/rgb_folder
# Output:
#   groundtruth_filter.txt (saved next to groundtruth.txt)

import sys
from pathlib import Path

EXTS = (".png", ".jpg", ".jpeg")

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 filter_gt_simple.py /path/to/groundtruth.txt /path/to/rgb_folder")
        sys.exit(1)
    gt_path = Path(sys.argv[1]).expanduser().resolve()
    rgb_dir = Path(sys.argv[2]).expanduser().resolve()

    if not gt_path.is_file():
        print(f"[Error] groundtruth not found: {gt_path}")
        sys.exit(2)
    if not rgb_dir.is_dir():
        print(f"[Error] rgb folder not found: {rgb_dir}")
        sys.exit(3)

    # Collect timestamp basenames from RGB folder
    img_ts = set()
    for ext in EXTS:
        for p in rgb_dir.rglob(f"*{ext}"):
            img_ts.add(p.stem)

    out_path = gt_path.with_name("groundtruth_filter.txt")

    kept = 0
    dropped = 0
    total = 0

    with gt_path.open("r", encoding="utf-8", errors="ignore") as fin,          out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            total += 1
            # Keep only if timestamp (first token) matches an image basename
            if parts[0] in img_ts:
                fout.write(line if line.endswith("\n") else line + "\n")
                kept += 1
            else:
                dropped += 1

    print(f"Done. Data lines: {total}, kept: {kept}, dropped: {dropped}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
