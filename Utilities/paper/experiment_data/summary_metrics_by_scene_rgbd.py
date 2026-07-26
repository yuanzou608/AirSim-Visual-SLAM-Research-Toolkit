#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import pandas as pd
import numpy as np

ROOT = os.path.abspath(".")

SCENES = ["building", "houses", "pool", "road", "roundabout"]

ALGO_TYPE_MAP = {
    "ORB-SLAM2": "Traditional",
    "ORB-SLAM3": "Traditional",
    "ElasticFusion": "Traditional",
    "DSO": "Traditional",
    "SVO": "Traditional",

    "DROID-SLAM": "Learning-based",
    "DPVO": "Learning-based",
    "TartanVO": "Learning-based",

    "MASt3R-SLAM": "Feedforward",
    "VGGT-SLAM": "Feedforward",
    "VGGT-LONG": "Feedforward",
    "SLAM3R": "Feedforward",

    "Photo-slam": "3DGS",
    "MongGS": "3DGS",
    "SplaTAM": "3DGS",
    "hierslam": "3DGS",
}

METRIC_MAP = {
    "ATE RMSE(m)": ("rmse_mean", "rmse_std"),
    "Peak VRAM(GB)": ("PeakReservedGB_mean", "PeakReservedGB_std"),
    "FPS": ("FPS_mean", "FPS_std"),
    "SR": ("SR", None),
}

COLUMNS = [
    "Type", "Algorithm", "Metric",
    "Building Mean", "Building STD",
    "Houses Mean", "Houses STD",
    "Pool Mean", "Pool STD",
    "Road Mean", "Road STD",
    "Roundabout Mean", "Roundabout STD",
    "Overall Mean", "Overall STD",
]


def load_scene_csv(csv_path, algorithm_label, algo_type):
    """加载 csv 并转换成 summary_metrics_with_mono 一行行结构"""
    df = pd.read_csv(csv_path)
    df["scene"] = df["scene"].str.lower().str.strip()

    scene_rows = {
        s: df[df["scene"] == s].iloc[0]
        for s in SCENES if (df["scene"] == s).any()
    }

    rows = []

    for metric_name, (mean_col, std_col) in METRIC_MAP.items():
        new_row = {col: "" for col in COLUMNS}
        new_row["Type"] = algo_type
        new_row["Algorithm"] = algorithm_label
        new_row["Metric"] = metric_name

        means = []
        stds = []

        for scene in SCENES:
            sr = scene_rows.get(scene)

            mean_val = None
            std_val = None

            if sr is not None:
                if metric_name == "SR":
                    mean_val = float(sr[mean_col])
                    std_val = np.nan
                else:
                    mean_val = float(sr[mean_col])
                    std_val = float(sr[std_col])

                means.append(mean_val)
                if std_col and not (isinstance(std_val, float) and math.isnan(std_val)):
                    stds.append(std_val)

            scene_cap = scene.capitalize() if scene != "roundabout" else "Roundabout"
            new_row[f"{scene_cap} Mean"] = mean_val
            new_row[f"{scene_cap} STD"] = std_val

        if means:
            new_row["Overall Mean"] = float(np.mean(means))
        if stds and metric_name != "SR":
            new_row["Overall STD"] = float(np.mean(stds))

        rows.append(new_row)

    return rows


def main():
    all_rows = []
    processed = []

    for algo in sorted(os.listdir(ROOT)):
        algo_dir = os.path.join(ROOT, algo)
        if not os.path.isdir(algo_dir):
            continue

        # 普通算法：summary_metrics_by_scene_mono.csv
        mono_csv = os.path.join(algo_dir, "summary_metrics_by_scene_rgbd.csv")


        algo_type = ALGO_TYPE_MAP.get(algo, "")

        # 处理普通算法
        if os.path.exists(mono_csv):
            all_rows += load_scene_csv(mono_csv, algo, algo_type)
            processed.append(algo)
            continue

    df = pd.DataFrame(all_rows, columns=COLUMNS)

    # 数字保留三位小数
    for col in COLUMNS[3:]:
        df[col] = df[col].apply(
            lambda x: f"{x:.3f}" if isinstance(x, (int, float, np.floating)) and not np.isnan(x) else ""
        )

    out_csv = os.path.join(ROOT, "summary_metrics_with_rgbd.csv")
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    print("处理了以下算法：")
    if processed:
        print("\n".join(processed))
    else:
        print("没有找到任何可处理的 CSV 文件。")


if __name__ == "__main__":
    main()
