# Audited memory only. For all modes without recomputing ATE, use
# Benchmark/experiment_data/normalize_memory_csvs.py (dry-run by default).
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory_gib import parse_peak_reserved_gib

from evo.tools import file_interface
from evo.core import sync
from evo.core.metrics import PoseRelation, APE
import os
import csv

def evaluate_ate_stats_like_cli(gt_file, est_file):
    if not (os.path.exists(gt_file) and os.path.exists(est_file)):
        return "NA"
    # 1. 读取 TUM 轨迹
    gt_traj = file_interface.read_tum_trajectory_file(gt_file)

    est_traj = file_interface.read_tum_trajectory_file(est_file)


    # 2. 时间同步：和 evo_ape 默认一样，用 max_diff = 0.01
    gt_sync, est_sync = sync.associate_trajectories(
        gt_traj, est_traj, max_diff=0.00
    )


    # 3. 先对齐：Umeyama + 尺度校正（Sim(3)）
    #   对齐的是 "估计轨迹 est_sync" 到 "gt_sync"
    est_sync.align(
        gt_sync,
        correct_scale=True,        # 等价于命令行的 --correct_scale
        correct_only_scale=False   # 同时做旋转+平移+尺度
    )

    # 4. 计算 APE w.r.t translation part —— 实际就是 ATE
    ape_metric = APE(PoseRelation.translation_part)
    ape_metric.process_data((gt_sync, est_sync))

    stats = ape_metric.get_all_statistics()  # dict

    results = {
        "max":   float(stats["max"]),
        "min":   float(stats["min"]),
        "mean":  float(stats["mean"]),
        "median": float(stats["median"]),
        "rmse":  float(stats["rmse"]),  # 论文里一般叫 ATE RMSE
        "sse":   float(stats["sse"]),
        "std":   float(stats["std"]),
    }
    return results

def parse_runtime_file(path):
    if not os.path.exists(path):
        return "NA", "NA"
    fps = None
    with open(path, "r") as f:
        for line in f:
            if "FPS_actual" in line:
                fps = float(line.split()[-1])
            if "Elapsed_Time_sec" in line:
                wall_clock = float(line.split()[-1])
    return fps, wall_clock

def parse_gpu_file(path):
    # Legacy CSV column PeakReservedGB is peak_reserved in GiB only after audit.
    # No allocated/device-used/RSS substitution; see ../memory_gib_audit.md.
    return parse_peak_reserved_gib(path, 'MASt3R-SLAM')




if __name__ == "__main__":
    dir = "/home/yuan/data2tb/dataset/my_data"
    # for dataset in sorted(os.listdir(dir)):
    #     print(dataset)

    dataset_list = [
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
        # "testdata"
    ]
    base = "/home/yuan/data2tb/experiments/MASt3R-SLAM/logs/airsim/nocalib"

    # 输出 CSV 路径（可按需修改）
    csv_path = os.path.join(base, "nocalib_metrics.csv")

    header = [
        "dataset",          # eg. road25fps_1
        "FPS",              # FPS_wall_clock
        "runtime",          # TotalWallClockTime_s
        "PeakReservedGB",   # legacy name; audited peak_reserved GiB; see memory_gib_metadata.json
        "max",
        "min",
        "mean",
        "median",
        "rmse",
        "sse",
        "std",
    ]

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for dataset in dataset_list:
            for run_id in ["1", "2", "3"]:
                dataset_name = f"{dataset}_{run_id}"

                gt = f"{base}/{dataset}/{run_id}/groundtruth.txt"
                est = f"{base}/{dataset}/{run_id}/FrameTrajectory.txt"
                runtime_path = f"{base}/{dataset}/{run_id}/metrics.txt"
                gpu_path = f"{base}/{dataset}/{run_id}/metrics.txt"
                # print(gt, est, runtime_path, gpu_path)

                ate_stats = evaluate_ate_stats_like_cli(gt, est)
                fps, wall_clock = parse_runtime_file(runtime_path)
                peak_gb = parse_gpu_file(gpu_path)

                if ate_stats == "NA":
                    max_v = min_v = mean_v = median_v = rmse_v = sse_v = std_v = "NA"
                else:
                    max_v   = ate_stats["max"]
                    min_v   = ate_stats["min"]
                    mean_v  = ate_stats["mean"]
                    median_v = ate_stats["median"]
                    rmse_v  = ate_stats["rmse"]
                    sse_v   = ate_stats["sse"]
                    std_v   = ate_stats["std"]

                row = [
                    dataset_name,
                    fps,
                    wall_clock,
                    peak_gb,
                    max_v,
                    min_v,
                    mean_v,
                    median_v,
                    rmse_v,
                    sse_v,
                    std_v,
                ]
                writer.writerow(row)

                print(f"written: {dataset_name}")

    print(f"\nSaved CSV to: {csv_path}")
