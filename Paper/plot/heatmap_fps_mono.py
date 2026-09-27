import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 场景类别
SCENES = ["building", "houses", "pool", "road", "roundabout"]


def get_scene_from_name(dataset_name: str):
    """
    根据 dataset 名称判断所属场景系列。
    例如: 'road25fps_1', 'houses_high_low_2', 'cross_building_high_high_3'
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


def main():
    ROOT = os.getcwd()  # 在 experiment_data 目录下运行
    method_dirs = [
        d for d in sorted(os.listdir(ROOT))
        if os.path.isdir(os.path.join(ROOT, d))
    ]

    # 保存 mean / count
    mean_fps = {}    # mean_fps[algo][scene] = float
    count_fps = {}   # count_fps[algo][scene] = int
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
            if not os.path.exists(csv_path):
                print(f"[跳过] {algo_name}: 找不到 {os.path.basename(csv_path)}")
                continue

            df = pd.read_csv(csv_path)
            # 需要 dataset 和 FPS 两列
            if "dataset" not in df.columns or "FPS" not in df.columns:
                print(f"[跳过] {algo_name}: 缺少 'dataset' 或 'FPS' 列")
                continue

            df["scene"] = df["dataset"].apply(get_scene_from_name)

            algo_names.append(algo_name)
            mean_fps.setdefault(algo_name, {})
            count_fps.setdefault(algo_name, {})

            for sc in SCENES:
                vals = df.loc[df["scene"] == sc, "FPS"].dropna().values
                if len(vals) > 0:
                    mean_fps[algo_name][sc] = float(np.mean(vals))
                    count_fps[algo_name][sc] = int(len(vals))
                else:
                    mean_fps[algo_name][sc] = np.nan
                    count_fps[algo_name][sc] = 0

    if not algo_names:
        print("没有任何算法的数据被成功读取。")
        return

    # 去重保持顺序
    algo_names = list(dict.fromkeys(algo_names))

    # ===== 打印每个算法、每个场景的实验数量 =====
    print("\nSample count for each algorithm & scene (FPS):")
    for algo in algo_names:
        print(f"\n{algo}:")
        for sc in SCENES:
            c = count_fps.get(algo, {}).get(sc, 0)
            print(f"  {sc:10s} -> {c}")
    print("\n")

    # ===== 构建 mean FPS 矩阵 (algo × scene) =====
    n_algo = len(algo_names)
    n_scene = len(SCENES)
    mat = np.full((n_algo, n_scene), np.nan, dtype=float)

    for i, algo in enumerate(algo_names):
        for j, sc in enumerate(SCENES):
            mat[i, j] = mean_fps.get(algo, {}).get(sc, np.nan)

    # ===== 绘制 heatmap =====
    fig, ax = plt.subplots(figsize=(8, 0.5 * n_algo + 3))

    im = ax.imshow(mat, aspect="auto")

    # 坐标轴标签
    ax.set_xticks(np.arange(n_scene))
    ax.set_xticklabels(SCENES)
    ax.set_yticks(np.arange(n_algo))
    ax.set_yticklabels(algo_names)

    plt.xlabel("Scene")
    plt.ylabel("SLAM method")
    plt.title("Mean FPS across scenes for each Monocular SLAM method")

    # 颜色条
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Mean FPS")

    # 在格子中写数值（保留两位小数）
    for i in range(n_algo):
        for j in range(n_scene):
            val = mat[i, j]
            if not np.isnan(val):
                ax.text(
                    j, i, f"{val:.2f}",
                    ha="center", va="center", fontsize=7, color="white"
                )

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
