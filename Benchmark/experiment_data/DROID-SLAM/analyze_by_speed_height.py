#!/usr/bin/env python3
import csv
import sys
import statistics
from collections import defaultdict

# 需要统计 mean/std 的所有 metric 列
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


def parse_speed_height_from_dataset(dataset_name: str):
    """
    从 dataset 名中提取速度(倒数第二) 和 高度(倒数第一)。
    示例:
        road2_low_medium_1 → speed=low, height=medium
        pool_high_low_2    → speed=high, height=low
        houses_medium_high_3 → speed=medium, height=high
    若最后两个字段不属于 {low, medium, high} 之一 → 不纳入统计。
    """
    levels = {"low", "medium", "high"}

    if not dataset_name:
        return None, None

    base = dataset_name.rsplit("_", 1)[0].lower()
    tokens = base.split("_")

    if len(tokens) < 2:
        return None, None

    speed = tokens[-2]
    height = tokens[-1]

    if speed in levels and height in levels:
        return speed, height
    return None, None


def to_float(val):
    """将数值转为 float；'NA' 返回 None"""
    if val is None:
        return None
    v = str(val).strip()
    if v.upper() == "NA" or v == "":
        return None
    try:
        return float(v)
    except:
        return None


def compute_group_stats(group_keys, group_values, metric_cols, out_csv):
    """
    生成一个 CSV 文件：
    group, SR, metric_mean, metric_std, ...
    """

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        header = ["group", "SR"]
        for m in metric_cols:
            header.append(f"{m}_mean")
            header.append(f"{m}_std")
        writer.writerow(header)

        for group in group_keys:
            total = group_values[group]["total"]
            success = group_values[group]["success"]
            sr = success / total if total > 0 else 0.0

            row = [group, sr]

            metrics_data = group_values[group]["metrics"]
            for m in metric_cols:
                vals = metrics_data[m]
                if len(vals) == 0:
                    mean_v = "NA"
                    std_v = "NA"
                else:
                    mean_v = sum(vals) / len(vals)
                    std_v = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                row.append(mean_v)
                row.append(std_v)

            writer.writerow(row)

    print(f"Saved: {out_csv}")


def main():
    # 输入的 metrics CSV
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = "mono_metrics.csv"

    speed_groups = ["speed_low", "speed_medium", "speed_high"]
    height_groups = ["height_low", "height_medium", "height_high"]

    # 初始化数据结构
    group_values = {}
    for g in speed_groups + height_groups:
        group_values[g] = {
            "total": 0,
            "success": 0,
            "metrics": {m: [] for m in METRIC_COLUMNS}
        }

    # 读取数据
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dataset_name = row["dataset"]
            speed_level, height_level = parse_speed_height_from_dataset(dataset_name)

            # 没有 speed+height 标签 → 不统计
            if speed_level is None or height_level is None:
                continue

            # 判断成功
            rmse_val = to_float(row["rmse"])
            is_success = rmse_val is not None

            # 分别加入速度/高度组
            speed_group = f"speed_{speed_level}"
            height_group = f"height_{height_level}"

            for group in [speed_group, height_group]:
                group_values[group]["total"] += 1

                if is_success:
                    group_values[group]["success"] += 1
                    # 记录 metrics 数值
                    for m in METRIC_COLUMNS:
                        v = to_float(row.get(m, "NA"))
                        if v is not None:
                            group_values[group]["metrics"][m].append(v)

    # 输出两个 CSV
    compute_group_stats(speed_groups, group_values, METRIC_COLUMNS,
                        "summary_metrics_by_speed.csv")

    compute_group_stats(height_groups, group_values, METRIC_COLUMNS,
                        "summary_metrics_by_height.csv")


if __name__ == "__main__":
    main()
