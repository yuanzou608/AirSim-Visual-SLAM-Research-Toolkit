#!/usr/bin/env python3
import csv
import sys
import statistics
from collections import defaultdict

# 哪些列要做 mean/std
METRIC_COLUMNS = [
    "FPS",
    "runtime",
    "PeakReservedGB",
    # "max",
    # "min",
    # "mean",
    # "median",
    "rmse",
    # "sse",
    # "std",
]

SCENE_KEYS = ["building", "houses", "pool", "road", "roundabout"]
SCENE_KEYS_WITH_OVERALL = SCENE_KEYS + ["overall"]


def get_scene_from_name(dataset_name: str):
    """
    dataset_name 例子： 'road25fps_1', 'houses_high_low_2'
    去掉 _1 / _2 / _3，然后按前缀判断所属场景系列。
    """
    base = dataset_name.rsplit("_", 1)[0].lower()

    if base.startswith("cross_building") or base.startswith("building"):
        return "building"
    if base.startswith("house"):
        return "houses"
    if base.startswith("pool"):
        return "pool"
    if base.startswith("road"):
        return "road"
    if base.startswith("roundabout"):
        return "roundabout"
    return None


def to_float_or_na(val):
    if val is None:
        return None
    v = str(val).strip()
    if v == "" or v.upper() == "NA":
        return None
    try:
        return float(v)
    except:
        return None


def main():
    dataset_sets = {scene: set() for scene in SCENE_KEYS}
    # 使用默认 CSV
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = "mono_metrics.csv"

    # 场景 → metric → list of float
    values = {
        scene: {m: [] for m in METRIC_COLUMNS}
        for scene in SCENE_KEYS_WITH_OVERALL
    }

    # 场景 → 总实验数 / 成功数
    total_counts = defaultdict(int)
    success_counts = defaultdict(int)

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:

            dataset_name = row["dataset"]
            scene = get_scene_from_name(dataset_name)
            # 去掉 _1/_2/_3，只保留 dataset 基本名
            base_dataset = dataset_name.rsplit("_", 1)[0]

            # 收集每个场景的 unique dataset
            if scene in SCENE_KEYS:
                dataset_sets[scene].add(base_dataset)
            # 如果无法判断场景类型，则归类为 overall（但不记录在五大类中）
            if scene is None:
                scene = None

            # 所有实验（overall 必须包含）
            total_counts["overall"] += 1

            rmse_val = to_float_or_na(row.get("rmse", "NA"))
            if rmse_val is not None:
                success_counts["overall"] += 1

            # 同时对 overall 累积数据（仅成功）
            if rmse_val is not None:
                for m in METRIC_COLUMNS:
                    v = to_float_or_na(row.get(m, "NA"))
                    if v is not None:
                        values["overall"][m].append(v)

            # 分类场景：只有属于五大类才统计
            if dataset_name is not None:
                real_scene = get_scene_from_name(dataset_name)
            else:
                real_scene = None

            if real_scene in SCENE_KEYS:
                total_counts[real_scene] += 1
                if rmse_val is not None:
                    success_counts[real_scene] += 1
                    for m in METRIC_COLUMNS:
                        v = to_float_or_na(row.get(m, "NA"))
                        if v is not None:
                            values[real_scene][m].append(v)

    # 写 summary 文件
    out_csv = "summary_metrics_by_scene_rgbd.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        header = ["scene", "SR"]
        for m in METRIC_COLUMNS:
            header.append(f"{m}_mean")
            header.append(f"{m}_std")
        writer.writerow(header)

        for scene in SCENE_KEYS_WITH_OVERALL:
            tot = total_counts.get(scene, 0)
            succ = success_counts.get(scene, 0)
            sr = succ / tot if tot > 0 else 0.0

            print(f"\n=== {scene} ===")
            print(f"total={tot}, success={succ}, SR={sr:.3f}")

            row = [scene, sr]

            for m in METRIC_COLUMNS:
                vals = values[scene][m]
                if len(vals) == 0:
                    mean_v = "NA"
                    std_v = "NA"
                    print(f"{m}: mean=NA, std=NA")
                else:
                    mean_v = sum(vals) / len(vals)
                    std_v = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                    print(f"{m}: mean={mean_v:.6f}, std={std_v:.6f}")
                row.append(mean_v)
                row.append(std_v)

            writer.writerow(row)
    print("\n==== Dataset Count per Scene ====")
    for scene in SCENE_KEYS:
        print(f"{scene}: {len(dataset_sets[scene])} datasets")
    print(f"\nSaved summary to: {out_csv}")


if __name__ == "__main__":
    main()
