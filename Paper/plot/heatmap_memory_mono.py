import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 场景类别
SCENES = ["building", "houses", "pool", "road", "roundabout"]


def get_scene_from_name(dataset_name: str):
    """
    根据 dataset 名称判断所属场景系列。
    building 场景包含 cross_building / building
    """
    base = dataset_name.rsplit("_", 1)[0].lower()

    if base.startswith("cross_building") or base.startswith("building"):
        return "building"
    if base.startswith("houses"):
        return "houses"
    if base.startswith("pool"):
        return "pool"
    if base.startswith("road"):
        return "road"
    if base.startswith("roundabout"):
        return "roundabout"
    return None


def load_metrics(csv_path, metric_name):
    """读取 metrics 文件（包含 dataset 和指定 metric），并把 metric 列转成数值。"""
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path)
    if "dataset" not in df.columns or metric_name not in df.columns:
        return None

    # 把 ('NA', 'NA')、'NA'、None 等全部转成 NaN，正常数字保留
    df[metric_name] = pd.to_numeric(df[metric_name], errors="coerce")

    df["scene"] = df["dataset"].apply(get_scene_from_name)
    return df


def main():
    ROOT = os.getcwd()  # 在 experiment_data 目录下运行

    method_dirs = [
        d for d in sorted(os.listdir(ROOT))
        if os.path.isdir(os.path.join(ROOT, d))
    ]

    metric = "PeakReservedGB"

    mean_metric = {}      # mean_metric[algo][scene]
    count_metric = {}     # count_metric[algo][scene]
    algo_names = []

    for method in method_dirs:
        method_path = os.path.join(ROOT, method)

        # ---- MASt3R-SLAM 特殊处理 ----
        if method.lower() == "mast3r-slam":
            csv_variants = {
                "MASt3R-SLAM (calib)": os.path.join(method_path, "calib_metrics.csv"),
                "MASt3R-SLAM (no calib)": os.path.join(method_path, "nocalib_metrics.csv"),
            }
        else:
            csv_variants = {
                method: os.path.join(method_path, "mono_metrics.csv")
            }

        for algo_name, csv_path in csv_variants.items():
            df = load_metrics(csv_path, metric)

            if df is None or len(df) == 0:
                print(f"[跳过] {algo_name}（找不到有效 {metric} 数据）")
                continue

            algo_names.append(algo_name)
            mean_metric.setdefault(algo_name, {})
            count_metric.setdefault(algo_name, {})

            for sc in SCENES:
                vals = df.loc[df["scene"] == sc, metric].dropna().values
                if len(vals) > 0:
                    mean_metric[algo_name][sc] = float(np.mean(vals))
                    count_metric[algo_name][sc] = int(len(vals))
                else:
                    mean_metric[algo_name][sc] = np.nan
                    count_metric[algo_name][sc] = 0

    if not algo_names:
        print("没有任何算法产生有效 PeakReservedGB 数据。")
        return

    algo_names = list(dict.fromkeys(algo_names))  # 去重保持顺序

    # ------- 打印每个算法、每个场景的实验数量 -------
    print("\nSample count for each algorithm & scene (PeakReservedGB):")
    for algo in algo_names:
        print(f"\n{algo}:")
        for sc in SCENES:
            print(f"  {sc:12s} -> {count_metric[algo].get(sc, 0)}")
    print("\n")

    # ------- 构建热力图矩阵 -------
    mat = np.full((len(algo_names), len(SCENES)), np.nan)

    for i, algo in enumerate(algo_names):
        for j, sc in enumerate(SCENES):
            mat[i, j] = mean_metric[algo].get(sc, np.nan)

    # ------- 绘制 Heatmap -------
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(algo_names) + 3))

    im = ax.imshow(mat, aspect="auto", cmap="viridis")

    # 坐标轴标签
    ax.set_xticks(np.arange(len(SCENES)))
    ax.set_xticklabels(SCENES)
    ax.set_yticks(np.arange(len(algo_names)))
    ax.set_yticklabels(algo_names)

    plt.xlabel("Scene")
    plt.ylabel("SLAM Method")
    plt.title("Mean Peak Memory (GB) Across Scenes for each Monocular SLAM method")

    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Mean Peak Reserved (GB)")

    # 在格子中写值（两位小数）
    for i in range(len(algo_names)):
        for j in range(len(SCENES)):
            val = mat[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color="white")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
