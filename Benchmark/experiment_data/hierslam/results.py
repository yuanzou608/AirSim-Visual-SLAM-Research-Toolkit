from evo.tools import file_interface
from evo.core import sync
from evo.core.metrics import PoseRelation, APE
import os
import csv

def evaluate_ate_stats_like_cli(gt_file, est_file):
    if not (os.path.exists(gt_file) and os.path.exists(est_file)):
        return "NA"
    try:
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
    except Exception as e:
        results = {
            "max": "NA",
            "min": "NA",
            "mean": "NA",
            "median": "NA",
            "rmse": "NA",  # 论文里一般叫 ATE RMSE
            "sse": "NA",
            "std": "NA",
        }
        return results

def parse_ATE(path):
    if not os.path.exists(path):
        return "NA"
    peak_reserved_mb = None
    with open(path, "r") as f:
        for line in f:
            ATE_RMSE_cm = float(line.split()[-1].strip())
            ATE_RMSE_m = ATE_RMSE_cm / 100
    return ATE_RMSE_m

def parse_runtime_file(path):
    if not os.path.exists(path):
        return "NA", "NA"
    fps = None
    with open(path, "r") as f:
        for line in f:
            if "FPS" in line:
                fps = float(line.split()[-1])
            if "Total Runtime" in line:
                wall_clock = float(line.split()[-1])
    return fps, wall_clock

def parse_gpu_file(path):
    if not os.path.exists(path):
        return "NA"
    peak_reserved_mb = None
    with open(path, "r") as f:
        for line in f:
            if "GPU Peak Memory" in line:
                peak_reserved_mb = float(line.split()[-1].strip())
    peak_reserved_gb = peak_reserved_mb / 1024.0 if peak_reserved_mb is not None else None
    return peak_reserved_gb




if __name__ == "__main__":
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
    # base = "/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_no_semantic" # no semantic dataset
    base = "/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_semantic" # semantic dataset

    # 输出 CSV 路径（可按需修改）
    csv_path = os.path.join("semantic_metrics_500frames.csv") # semantic dataset
    # csv_path = os.path.join("rgbd_metrics_500frames.csv") # rgbd dataset

    header = [
        "dataset",          # eg. road25fps_1
        "FPS",              # FPS_wall_clock
        "runtime",          # TotalWallClockTime_s
        "PeakReservedGB",   # peak reserved in GB
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
            for run_id in ["4", "5", "6"]:
                dataset_name = f"{dataset}_{run_id}"

                gt = f"{base}/{dataset}/500frames/{run_id}/groundtruth_tum.txt"
                est = f"{base}/{dataset}/500frames/{run_id}/estimate_tum.txt"
                # ATE_RMSE_path = f"{base}/{dataset}/500frames/{run_id}/eval/ATE.txt"
                runtime_path = f"{base}/{dataset}/500frames/{run_id}/metric.txt"
                gpu_path = f"{base}/{dataset}/500frames/{run_id}/metric.txt"
                # print(gt, est, runtime_path, gpu_path)

                # rmse_v = parse_ATE(ATE_RMSE_path)
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
