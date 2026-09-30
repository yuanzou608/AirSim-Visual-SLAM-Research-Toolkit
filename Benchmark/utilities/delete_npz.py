#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""递归清理 Hier-SLAM 文件夹中的 .npz 文件（仅使用 Python 标准库）。

默认只预览：
    python3 delete_npz.py
真正删除：
    python3 delete_npz.py --delete
指定其他目录：
    python3 delete_npz.py /path/to/hierslam --delete

注意：删除不会进入回收站；包括 params.npz 在内的所有 .npz 文件都会匹配。
不遍历符号链接目录；对 .npz 文件符号链接，只删除链接，不删除链接目标。
"""

import argparse
import os
import stat
import sys
from pathlib import Path


DEFAULT_FOLDER = "/home/yuan/SLAM"


def format_size(size: int) -> str:
    """格式化逻辑文件大小，不代表实际释放的磁盘空间。"""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="递归清理指定文件夹下所有 .npz 文件，默认只预览，不删除。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "folder", nargs="?", default=str(DEFAULT_FOLDER), help="待清理的根目录"
    )
    parser.add_argument(
        "--delete", action="store_true", help="执行永久删除；不加此参数时仅预览"
    )
    args = parser.parse_args()

    try:
        root = Path(args.folder).expanduser().resolve(strict=True)
        if not root.is_dir():
            parser.error(f"不是文件夹：{root}")
        if root == Path(root.anchor):
            parser.error("为避免误删，不允许以文件系统根目录为清理目标。")
    except (OSError, RuntimeError) as exc:
        parser.error(f"无法访问目标目录：{exc}")

    errors = 0
    matched = 0
    completed = 0
    total_bytes = 0

    def report_scan_error(exc: OSError) -> None:
        nonlocal errors
        errors += 1
        print(f"[扫描失败] {exc}", file=sys.stderr)

    print(f"目标目录：{root}")
    print("模式：永久删除" if args.delete else "模式：仅预览（不会删除任何文件）")
    print("匹配：所有子目录中的 .npz 文件（扩展名不区分大小写）\n")

    for directory, subdirs, filenames in os.walk(
        root, followlinks=False, onerror=report_scan_error
    ):
        subdirs.sort()
        for name in sorted(filenames):
            if Path(name).suffix.lower() != ".npz":
                continue
            path = Path(directory) / name
            try:
                info = path.lstat()
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                    continue
                matched += 1
                is_link = stat.S_ISLNK(info.st_mode)
                # 符号链接不计入文件内容总大小，不会删除它所指向的文件。
                size = 0 if is_link else info.st_size
                label = "符号链接" if is_link else format_size(size)
                if args.delete:
                    path.unlink()
                    action = "已删除"
                else:
                    action = "待删除"
                completed += 1
                total_bytes += size
                print(f"[{action}] {path} ({label})")
            except OSError as exc:
                errors += 1
                print(f"[处理失败] {path}: {exc}", file=sys.stderr)

    print("\n" + "=" * 60)
    print(f"匹配数量：{matched}")
    print(f"{'已删除数量' if args.delete else '预览数量'}：{completed}")
    print(f"{'已删除文件总大小' if args.delete else '待删除文件总大小'}：{format_size(total_bytes)}")
    print(f"错误数量：{errors}")
    if errors:
        print("存在扫描或处理失败，请查看上面的错误信息；结果可能不完整。")
    if not args.delete:
        print("当前未删除任何文件。确认目标和列表后，加 --delete 参数执行删除。")
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断；此前已完成的删除不会撤销。", file=sys.stderr)
        raise SystemExit(130)
