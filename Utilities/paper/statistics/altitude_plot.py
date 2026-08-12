import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---------- speed / height 映射 ----------
SPEED_MAP = {"low": 2, "medium": 4, "high": 8}       # m/s
HEIGHT_MAP = {"low": 10, "medium": 20, "high": 30}   # m

SPEED_LEVELS = [2, 4, 8]          # 不同速度
HEIGHT_LEVELS = [10, 20, 30]      # 不同高度
HEIGHT_LABELS = {10: "10m (low)", 20: "20m (medium)", 30: "30m (high)"}


def parse_speed_height(dataset_name: str):
    """
    从数据集名字解析速度和高度。
    如: cross_building_high_low_1 -> speed=high(8m/s), height=low(10m)
    """
    parts = dataset_name.lower().split("_")
    if len(parts) < 3:
        return None, None

    speed_level = parts[-3]    # low / medium / high
    height_level = parts[-2]

    speed = SPEED_MAP.get(speed_level)
    height = HEIGHT_MAP.get(height_level)
    return speed, height


def load_df_with_speed_height(csv_path):
    """读取一个 metrics csv，并解析出 speed / height 列。"""
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path)
    if "dataset" not in df.columns or "rmse" not in df.columns:
        return None

    df["speed"], df["height"] = zip(*df["dataset"].map(parse_speed_height))
    df = df.dropna(subset=["speed", "height", "rmse"])  # 去掉解析失败或 rmse 为 NA 的
    return df


def main():
    ROOT = os.getcwd()   # 在 experiment_data 目录下运行
    method_dirs = [d for d in sorted(os.listdir(ROOT)) if os.path.isdir(os.path.join(ROOT, d))]

    method_names = []
    stats = {}   # stats[method_name] = DataFrame(index=(speed,height), columns=[mean,count])

    print("\n============ Speed fixed, color = height ============\n")

    for method in method_dirs:
        method_path = os.path.join(ROOT, method)

        # 特殊处理 MASt3R-SLAM
        if method.lower() == "mast3r-slam":
            variants = {
                "MASt3R-SLAM (calib)": os.path.join(method_path, "calib_metrics.csv"),
                # "MASt3R-SLAM (no calib)": os.path.join(method_path, "nocalib_metrics.csv"),
            }
        else:
            variants = {
                method: os.path.join(method_path, "mono_metrics.csv")
            }

        for name, csv_path in variants.items():
            df = load_df_with_speed_height(csv_path)
            if df is None or len(df) == 0:
                print(f"[跳过] {name}: 无有效数据")
                continue

            method_names.append(name)

            gb = df.groupby(["speed", "height"])["rmse"].agg(["mean", "count"])
            stats[name] = gb

            print(f"\n---- {name} ----")
            print(f"总实验数量: {len(df)}")
            for spd in SPEED_LEVELS:
                for h in HEIGHT_LEVELS:
                    key = (spd, h)
                    c = int(gb.loc[key, "count"]) if key in gb.index else 0
                    print(f"速度 {spd} m/s, 高度 {h} m -> 样本数: {c}")

    if not method_names:
        print("没有任何方法有有效数据。")
        return

    # 去重保持顺序
    method_names = list(dict.fromkeys(method_names))

    # ---------- 绘制 3 张柱状图：每张图固定一个速度 ----------
    for spd in SPEED_LEVELS:
        plt.figure(figsize=(12, 5))

        x = np.arange(len(method_names))  # 每个方法一个 x
        n_heights = len(HEIGHT_LEVELS)
        total_width = 0.8
        bar_width = total_width / n_heights

        for i, h in enumerate(HEIGHT_LEVELS):
            means = []
            for mname in method_names:
                gb = stats.get(mname)
                if gb is not None and (spd, h) in gb.index:
                    means.append(gb.loc[(spd, h), "mean"])
                else:
                    means.append(np.nan)

            offsets = x - total_width/2 + (i + 0.5) * bar_width
            plt.bar(offsets, means, width=bar_width, label=HEIGHT_LABELS[h])

        plt.xticks(x, method_names, rotation=45, ha="right")
        plt.ylabel("Mean RMSE")
        plt.title(f"Speed = {spd} m/s")
        plt.grid(True, axis="y", linestyle="--", alpha=0.5)
        plt.legend(title="Height", fontsize=8)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
