#!/usr/bin/env python3
"""Replace TUM timestamps with indices starting at 1.0 in increments of 0.1.

The original eight-column filtering, numeric formatting and batch sequence
list are preserved. Select an input file or an explicit batch dataset root.
"""

import argparse
from pathlib import Path

DEFAULT_DATASETS = [
    "building25fps",
    "cross_building_high_high",
    "cross_building_high_low",
    "cross_building_high_medium",
    "cross_building_low_high",
    "cross_building_low_low",
    "cross_building_low_medium",
    "cross_building_medium_high",
    "cross_building_medium_low",
    "cross_building_medium_medium",
    "houses_high_high",
    "houses_high_low",
    "houses_high_medium",
    "houses_low_high",
    "houses_low_low",
    "houses_low_medium",
    "houses_medium_high",
    "houses_medium_low",
    "houses_medium_medium",
    "pool_high_high",
    "pool_high_low",
    "pool_high_medium",
    "pool_low_high",
    "pool_low_low",
    "pool_low_medium",
    "pool_medium_high",
    "pool_medium_low",
    "pool_medium_medium",
    "road25fps",
    "road2_high_high",
    "road2_high_low",
    "road2_high_medium",
    "road2_low_high",
    "road2_low_low",
    "road2_low_medium",
    "road2_medium_high",
    "road2_medium_low",
    "road2_medium_medium",
    "roundabout25fps",
    "roundabout2_high_high",
    "roundabout2_high_low",
    "roundabout2_high_medium",
    "roundabout2_low_high",
    "roundabout2_low_low",
    "roundabout2_low_medium",
    "roundabout2_medium_high",
    "roundabout2_medium_low",
    "roundabout_square25fps",
    "testdata"
]


def groundtruth2index(input_file, output_file):
    start = 1.0
    step = 0.1

    with open(input_file, "r") as fin, open(output_file, "w") as fout:
        current = start
        for line in fin:
            line = line.strip()
            if line == "":
                continue

            parts = line.split()

            # 8 列：timestamp tx ty tz qx qy qz qw
            if len(parts) != 8:
                print("Skip malformed line:", line)
                continue

            # 替换 timestamp
            parts[0] = f"{current:.6f}"
            current += step

            fout.write(" ".join(parts) + "\n")

    print("Done! Modified file saved as:", output_file)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Single ground-truth file")
    source.add_argument("--dataset-root", type=Path,
                        help="Batch root containing DATASET/groundtruth.txt")
    parser.add_argument("--output", type=Path, help="Required with --input")
    parser.add_argument("--datasets", nargs="+",
                        help="Batch sequence names (default: original sequence list)")
    args = parser.parse_args(argv)
    if args.input is not None:
        if args.output is None or args.datasets is not None:
            parser.error("--input requires --output and cannot be combined with --datasets")
        if args.input.resolve() == args.output.resolve():
            parser.error("--input and --output must be different files")
        groundtruth2index(args.input, args.output)
    else:
        if args.output is not None:
            parser.error("--output requires --input; batch output is DATASET/groundtruth_index.txt")
        for dataset in args.datasets if args.datasets is not None else DEFAULT_DATASETS:
            folder = args.dataset_root / dataset
            groundtruth2index(folder / "groundtruth.txt", folder / "groundtruth_index.txt")


if __name__ == "__main__":
    main()
