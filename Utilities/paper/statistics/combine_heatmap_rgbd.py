import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

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


def load_metrics(csv_path):
    """
    读取一个 metrics csv，返回包含：
    dataset, rmse, FPS, PeakReservedGB, scene
    并把数值列强制转成 float，无法解析的设为 NaN。
    """
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path)
    if "dataset" not in df.columns:
        return None

    # 有些算法可能没有 rmse / FPS / PeakReservedGB，先统一创建列
    for col in ["rmse", "FPS", "PeakReservedGB"]:
        if col not in df.columns:
            df[col] = np.nan

    # 转成数值，'NA'、('NA','NA') 等会变成 NaN
    df["rmse"] = pd.to_numeric(df["rmse"], errors="coerce")
    df["FPS"] = pd.to_numeric(df["FPS"], errors="coerce")
    df["PeakReservedGB"] = pd.to_numeric(df["PeakReservedGB"], errors="coerce")

    df["scene"] = df["dataset"].apply(get_scene_from_name)
    return df


def main():
    ROOT = os.getcwd()  # 在 experiment_data 目录运行
    method_dirs = [
        d for d in sorted(os.listdir(ROOT))
        if os.path.isdir(os.path.join(ROOT, d))
    ]

    mean_rmse = {}
    mean_fps = {}
    mean_mem = {}
    count_rmse = {}
    algo_names = []

    for method in method_dirs:
        method_path = os.path.join(ROOT, method)


        csv_variants = {
                method: os.path.join(method_path, "rgbd_metrics.csv")
            }

        for algo_name, csv_path in csv_variants.items():
            df = load_metrics(csv_path)
            if df is None or len(df) == 0:
                print(f"[跳过] {algo_name}: 没有有效数据")
                continue

            algo_names.append(algo_name)
            mean_rmse.setdefault(algo_name, {})
            mean_fps.setdefault(algo_name, {})
            mean_mem.setdefault(algo_name, {})
            count_rmse.setdefault(algo_name, {})

            for sc in SCENES:
                sub = df[df["scene"] == sc]

                # RMSE
                vals_r = sub["rmse"].dropna().values
                if len(vals_r) > 0:
                    mean_rmse[algo_name][sc] = float(np.mean(vals_r))
                    count_rmse[algo_name][sc] = int(len(vals_r))
                else:
                    mean_rmse[algo_name][sc] = np.nan
                    count_rmse[algo_name][sc] = 0

                # FPS
                vals_f = sub["FPS"].dropna().values
                mean_fps[algo_name][sc] = float(np.mean(vals_f)) if len(vals_f) > 0 else np.nan

                # PeakReservedGB
                vals_m = sub["PeakReservedGB"].dropna().values
                mean_mem[algo_name][sc] = float(np.mean(vals_m)) if len(vals_m) > 0 else np.nan

    if not algo_names:
        print("没有任何算法的数据。")
        return

    # 去重保持顺序
    algo_names = list(dict.fromkeys(algo_names))

    # ===== 打印每个算法、每个场景的样本数量（按 RMSE 统计） =====
    print("\nSample count for each algorithm & scene (RMSE)：")
    for algo in algo_names:
        print(f"\n{algo}:")
        for sc in SCENES:
            print(f"  {sc:12s} -> {count_rmse[algo].get(sc, 0)}")
    print()

    # ===== 构建三个矩阵：algo × scene =====
    n_algo = len(algo_names)
    n_scene = len(SCENES)

    mat_rmse = np.full((n_algo, n_scene), np.nan)
    mat_fps = np.full((n_algo, n_scene), np.nan)
    mat_mem = np.full((n_algo, n_scene), np.nan)

    for i, algo in enumerate(algo_names):
        for j, sc in enumerate(SCENES):
            mat_rmse[i, j] = mean_rmse[algo].get(sc, np.nan)
            mat_fps[i, j] = mean_fps[algo].get(sc, np.nan)
            mat_mem[i, j] = mean_mem[algo].get(sc, np.nan)

    # ===== 画 1×3 合并图 =====
    fig, axes = plt.subplots(
        1, 3,
        figsize=(18, 0.5 * n_algo + 3),
        sharey=True
    )

    # 左：RMSE
    im0 = axes[0].imshow(mat_rmse, aspect="auto", cmap="viridis")
    axes[0].set_xticks(np.arange(n_scene))
    axes[0].set_xticklabels(SCENES, rotation=30, ha="right")
    axes[0].set_yticks(np.arange(n_algo))
    axes[0].set_yticklabels(algo_names)
    axes[0].set_xlabel("Scene")
    axes[0].set_ylabel("SLAM method")
    axes[0].set_title("Mean RMSE")

    cbar0 = fig.colorbar(im0, ax=axes[0])
    cbar0.set_label("Mean RMSE")

    # 中：FPS
    im1 = axes[1].imshow(mat_fps, aspect="auto", cmap="viridis_r")
    axes[1].set_xticks(np.arange(n_scene))
    axes[1].set_xticklabels(SCENES, rotation=30, ha="right")
    axes[1].set_xlabel("Scene")
    axes[1].set_title("Mean FPS")
    axes[1].tick_params(axis="y", labelleft=False)  # 共用左侧 y 标签

    cbar1 = fig.colorbar(im1, ax=axes[1])
    cbar1.set_label("Mean FPS")

    # 右：Memory
    im2 = axes[2].imshow(mat_mem, aspect="auto", cmap="viridis")
    axes[2].set_xticks(np.arange(n_scene))
    axes[2].set_xticklabels(SCENES, rotation=30, ha="right")
    axes[2].set_xlabel("Scene")
    axes[2].set_title("Mean Peak Reserved (GB)")
    axes[2].tick_params(axis="y", labelleft=False)

    cbar2 = fig.colorbar(im2, ax=axes[2])
    cbar2.set_label("Mean PeakReservedGB (GB)")

    # 在格子里写数值（可以只给 RMSE / 任选）
    for i in range(n_algo):
        for j in range(n_scene):
            val = mat_rmse[i, j]
            if not np.isnan(val):
                axes[0].text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=6, color="white")

            val_f = mat_fps[i, j]
            if not np.isnan(val_f):
                axes[1].text(j, i, f"{val_f:.1f}", ha="center", va="center", fontsize=6, color="white")

            val_m = mat_mem[i, j]
            if not np.isnan(val_m):
                axes[2].text(j, i, f"{val_m:.2f}", ha="center", va="center", fontsize=6, color="white")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
