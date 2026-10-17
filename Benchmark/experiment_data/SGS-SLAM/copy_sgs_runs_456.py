#!/usr/bin/env python3
"""将 SGS-SLAM 各实验场景中的 4/5/6 文件夹复制到对应归档目录。"""

import argparse
import shutil
from pathlib import Path

SOURCE = Path('/home/yuan/SLAM/SGS-SLAM/SGS-SLAM/experiments/Airsim_semantic')
TARGET = Path('/home/yuan/data2tb/experiments/SGS-SLAM/experiments/Airsim_semantic')
RUN_DIRS = ('4', '5', '6')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='只预览复制内容，不修改文件')
    args = parser.parse_args()

    if not SOURCE.is_dir():
        parser.error(f'源目录不存在: {SOURCE}')
    if not TARGET.is_dir():
        parser.error(f'目标根目录不存在: {TARGET}')

    copied = 0
    missing = 0
    for scene in sorted(SOURCE.iterdir()):
        if not scene.is_dir():
            continue

        target_scene = TARGET / scene.name
        if not target_scene.is_dir():
            print(f'[跳过] 目标场景目录不存在: {target_scene}')
            missing += 1
            continue

        for run_name in RUN_DIRS:
            source_run = scene / run_name
            if not source_run.is_dir():
                print(f'[跳过] 源目录不存在: {source_run}')
                missing += 1
                continue

            target_run = target_scene / run_name
            print(f'[{"预览" if args.dry_run else "复制"}] {source_run} -> {target_run}')
            if not args.dry_run:
                shutil.copytree(source_run, target_run, dirs_exist_ok=True)
            copied += 1

    print(f'\n完成：{copied} 个待复制/已复制目录，{missing} 个缺失项。'
          + ('（仅预览，没有修改文件）' if args.dry_run else ''))


if __name__ == '__main__':
    main()
