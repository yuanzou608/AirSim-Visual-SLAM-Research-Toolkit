#!/usr/bin/env python3
# 用法：
#   python add_ts_from_gt.py groundtruth.txt traj_est.txt traj_est_tum.txt
# 说明：
#   从 groundtruth.txt 读取每行首列 timestamp（跳过空行和以 # 开头的行），
#   与 7 列轨迹逐行对齐（按最短长度截断），输出 TUM 格式：
#   timestamp tx ty tz qx qy qz qw

import sys
import numpy as np

def load_timestamps(gt_path):
    ts = []
    with open(gt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            ts.append(float(s.split()[0]))
    return np.asarray(ts, dtype=float)

def main():
    if len(sys.argv) != 4:
        print("Usage: python add_ts_from_gt.py <groundtruth.txt> <in7.txt> <out_tum.txt>")
        sys.exit(1)

    gt_path, in7_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    ts = load_timestamps(gt_path)           # 读取时间戳
    arr7 = np.loadtxt(in7_path)             # 读取 7 列轨迹
    if arr7.ndim == 1:
        arr7 = arr7[None, :]                # 兼容单行

    n = min(len(ts), len(arr7))             # 按最短对齐
    out = np.column_stack([ts[:n], arr7[:n]])
    np.savetxt(out_path, out,
               fmt="%.9f %.6f %.6f %.6f %.6f %.6f %.6f %.6f")
    print(f"[OK] wrote {out_path}  rows={n}")

if __name__ == "__main__":
    main()
