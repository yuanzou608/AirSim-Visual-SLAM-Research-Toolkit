#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert GT/EST trajectories to KITTI 12-column format.

Usage:
  python3 json2kitty.py --gt traj.txt --est trj_final.json \
      --out-gt gt_kitti.txt --out-est est_kitti.txt
  # 也支持 16 列/12 列 txt 或 trj_final.json
"""

import argparse, os, json, sys
from typing import List

def write_kitti_txt(path: str, rows: List[List[float]], precision: int = 10):
    fmt = f"{{:.{precision}e}}"
    with open(path, "w") as f:
        for r in rows:
            if len(r) != 12:
                continue
            f.write(" ".join(fmt.format(v) for v in r) + "\n")

def txt_to_kitti12(path: str) -> List[List[float]]:
    """支持 16 列(4x4) 与 12 列，两者都输出为 12 列。"""
    rows = []
    with open(path, "r") as f:
        for ln in f:
            xs = ln.strip().split()
            if not xs:
                continue
            try:
                vals = [float(x) for x in xs]
            except ValueError:
                continue
            if len(vals) == 16:
                # 取前三行(3x4)=12 个数（KITTI）
                rows.append(vals[0:4] + vals[4:8] + vals[8:12])
            elif len(vals) == 12:
                rows.append(vals)
            else:
                # 其他长度忽略
                continue
    return rows

def _flatten_row_major(m):
    flat = []
    for r in m:
        if isinstance(r, (list, tuple)):
            flat.extend([float(x) for x in r])
        else:
            flat.append(float(r))
    return flat

def json_to_kitti12(path: str) -> List[List[float]]:
    """兼容常见字段: trj_est / traj_est / poses / traj / est 或顶层 list。"""
    with open(path, "r") as f:
        data = json.load(f)

    poses = None
    if isinstance(data, dict):
        for k in ("trj_est", "traj_est", "poses", "traj", "est"):
            if k in data and isinstance(data[k], list):
                poses = data[k]
                break
    if poses is None and isinstance(data, list):
        poses = data
    if poses is None:
        raise RuntimeError("Cannot find pose list in JSON (trj_est/traj_est/poses/...).")

    rows = []
    for M in poses:
        # 允许 {"matrix": [...]}
        if isinstance(M, dict) and "matrix" in M:
            M = M["matrix"]
        flat = _flatten_row_major(M)
        if len(flat) == 16:
            rows.append(flat[0:4] + flat[4:8] + flat[8:12])
        elif len(flat) == 12:
            rows.append(flat)
        else:
            # 跳过不合规
            continue
    return rows

def to_kitti12_auto(in_path: str) -> List[List[float]]:
    if not os.path.exists(in_path):
        raise FileNotFoundError(in_path)
    if in_path.lower().endswith(".json"):
        return json_to_kitti12(in_path)
    return txt_to_kitti12(in_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True, help="GT: 16/12 列 txt 或 .json")
    ap.add_argument("--est", required=True, help="EST: 16/12 列 txt 或 .json")
    ap.add_argument("--out-gt", default="gt_kitti.txt")
    ap.add_argument("--out-est", default="est_kitti.txt")
    ap.add_argument("--precision", type=int, default=10)
    args = ap.parse_args()

    gt_rows = to_kitti12_auto(args.gt)
    est_rows = to_kitti12_auto(args.est)

    if not gt_rows:
        print(f"[error] no valid rows parsed from GT: {args.gt}", file=sys.stderr)
        sys.exit(1)
    if not est_rows:
        print(f"[error] no valid rows parsed from EST: {args.est}", file=sys.stderr)
        sys.exit(1)

    write_kitti_txt(args.out_gt, gt_rows, precision=args.precision)
    write_kitti_txt(args.out_est, est_rows, precision=args.precision)

    print(f"[ok] GT  -> {args.out_gt} ({len(gt_rows)} lines)")
    print(f"[ok] EST -> {args.out_est} ({len(est_rows)} lines)")
    print("Tip: evo_ape kitti", args.out_gt, args.out_est, "-a -p --correct_scale")

if __name__ == "__main__":
    main()
