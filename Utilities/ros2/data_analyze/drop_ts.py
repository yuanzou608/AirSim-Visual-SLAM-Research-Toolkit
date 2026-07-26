#!/usr/bin/env python3
# 用法：
#   python drop_ts_one.py /path/to/groundtruth.txt
# 说明：
#   读取 groundtruth.txt（TUM风格：timestamp tx ty tz qx qy qz qw ...）
#   忽略空行与以 # 开头的注释行
#   去掉首列 timestamp，只保留后7列
#   输出到同目录：groundtruth_no_ts.txt

import sys
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: python drop_ts_one.py /path/to/groundtruth.txt")
        sys.exit(1)

    in_path = Path(sys.argv[1]).expanduser().resolve()
    if not in_path.is_file():
        print(f"[Error] file not found: {in_path}")
        sys.exit(2)

    out_path = in_path.with_name("groundtruth_no_ts.txt")

    kept = 0
    skipped = 0
    with in_path.open("r", encoding="utf-8", errors="ignore") as fin, \
         out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            s = line.strip()
            if not s or s.startswith("#"):
                skipped += 1
                continue
            parts = s.split()
            if len(parts) >= 8:
                fout.write(" ".join(parts[1:8]) + "\n")
                kept += 1
            else:
                skipped += 1

    print(f"[OK] wrote: {out_path}  kept={kept}  skipped={skipped}")

if __name__ == "__main__":
    main()
