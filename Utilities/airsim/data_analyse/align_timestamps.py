# Create a Python script that aligns timestamps:
# - Reads groundtruth.txt (TUM format with timestamps)
# - Reads est_c2w_tum.txt (index + pose without timestamps)
# - Chooses N = min(len(gt), len(est))
# - Writes:
#   * out_gt: first N lines from groundtruth (unchanged)
#   * out_est: first N lines from est but with timestamps replaced by the first N timestamps from groundtruth
# Usage:
#   python3 align_timestamps.py --gt groundtruth.txt --est est_c2w_tum.txt --out-gt gt_synced.txt --out-est est_synced.txt

#!/usr/bin/env python3
import argparse
from pathlib import Path

def read_lines(path):
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for ln in f:
            s = ln.strip()
            if not s or s.startswith('#'):
                continue
            lines.append(s)
    return lines

def parse_gt_lines(lines):
    """Return list of [timestamp_str, tx, ty, tz, qx, qy, qz, qw] as strings (preserve precision)."""
    out = []
    for i, s in enumerate(lines):
        parts = s.split()
        if len(parts) < 8:
            raise ValueError(f"GT line {i} has {len(parts)} fields, expected >= 8: {s}")
        # Keep as strings to preserve original precision
        out.append(parts[:8])
    return out

def parse_est_lines(lines):
    """Return list of [tx, ty, tz, qx, qy, qz, qw] as strings (drop leading index/frame-id)."""
    out = []
    for i, s in enumerate(lines):
        parts = s.split()
        if len(parts) < 8:
            raise ValueError(f"EST line {i} has {len(parts)} fields, expected >= 8: {s}")
        # est_c2w_tum.txt appears as: idx tx ty tz qx qy qz qw
        # We drop the first token (idx) and keep the 7 pose values
        pose7 = parts[1:8]
        if len(pose7) != 7:
            raise ValueError(f"EST line {i} malformed after dropping index: {s}")
        out.append(pose7)
    return out

def write_gt(path, gt_firstN):
    with open(path, 'w', encoding='utf-8') as f:
        for row in gt_firstN:
            f.write(' '.join(row) + '\n')

def write_est_with_gt_timestamps(path, gt_firstN, est_pose7_firstN):
    with open(path, 'w', encoding='utf-8') as f:
        for ts_pose, pose7 in zip(gt_firstN, est_pose7_firstN):
            timestamp = ts_pose[0]
            f.write(' '.join([timestamp] + pose7) + '\n')

def main():
    ap = argparse.ArgumentParser(description="Align timestamps: use groundtruth's first N timestamps for est poses.")
    ap.add_argument('--gt', type=str, default='groundtruth.txt', help='Path to groundtruth TUM file (with timestamps).')
    ap.add_argument('--est', type=str, default='est_c2w_tum.txt', help='Path to est file (index + pose).')
    ap.add_argument('--out-gt', type=str, default='gt_synced.txt', help='Output GT (first N lines).')
    ap.add_argument('--out-est', type=str, default='est_synced.txt', help='Output EST with GT timestamps.')
    args = ap.parse_args()

    gt_lines = read_lines(args.gt)
    est_lines = read_lines(args.est)

    gt_parsed = parse_gt_lines(gt_lines)
    est_parsed = parse_est_lines(est_lines)

    N = min(len(gt_parsed), len(est_parsed))
    if N == 0:
        raise SystemExit("No overlapping lines to align (N=0). Check your input files.")

    gt_firstN = gt_parsed[:N]
    est_firstN = est_parsed[:N]

    write_gt(args.out_gt, gt_firstN)
    write_est_with_gt_timestamps(args.out_est, gt_firstN, est_firstN)

    print(f"Aligned N = {N} frames.")
    print(f"Wrote: {args.out_gt} (first N GT lines)")
    print(f"Wrote: {args.out_est} (EST with GT timestamps)")

if __name__ == '__main__':
    main()


