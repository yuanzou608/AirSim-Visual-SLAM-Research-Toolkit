import os
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
    # 在 experiment_data 目录下运行
    ROOT = os.getcwd()

    # 所有算法子目录
    method_dirs = [
        d for d in sorted(os.listdir(ROOT))
        if os.path.isdir(os.path.join(ROOT, d))
    ]

    # data_by_scene[scene][method] = list of rmse
    data_by_scene = {sc: {} for sc in SCENES}
    counts_by_scene = {sc: {} for sc in SCENES}

    method_names = []  # 记录真正有数据的“算法名”（包括 MASt3R-SLAM 两个变体）

    for method in method_dirs:
        method_path = os.path.join(ROOT, method)

        # === 特殊处理 MASt3R-SLAM ===
        if method.lower() == "mast3r-slam":
            csv_variants = {
                "MASt3R-SLAM (calib)": os.path.join(method_path, "calib_metrics.csv"),
                "MASt3R-SLAM (no calib)": os.path.join(method_path, "nocalib_metrics.csv"),
            }
        else:
            csv_variants = {
                method: os.path.join(method_path, "mono_metrics.csv")
            }

        # 遍历这个目录下的一个或多个 csv（普通算法只有一个，MASt3R 两个）
        for algo_name, csv_path in csv_variants.items():
            if not os.path.exists(csv_path):
                print(f"[跳过] {algo_name}: 找不到 {os.path.basename(csv_path)}")
                continue

            df = pd.read_csv(csv_path)
            if "dataset" not in df.columns or "rmse" not in df.columns:
                print(f"[跳过] {algo_name}: 缺少 'dataset' 或 'rmse' 列")
                continue

            # 识别场景
            df["scene"] = df["dataset"].apply(get_scene_from_name)

            method_names.append(algo_name)

            for sc in SCENES:
                vals = df.loc[df["scene"] == sc, "rmse"].dropna().values
                data_by_scene[sc][algo_name] = vals
                counts_by_scene[sc][algo_name] = len(vals)

    if not method_names:
        print("没有任何算法的数据被成功读取。")
        return

    # 去重保持顺序
    method_names = list(dict.fromkeys(method_names))

    # ===== 打印每个算法在每个场景的样本数量 =====
    print("\n样本数量 (algorithm, scene):")
    for algo in method_names:
        for sc in SCENES:
            c = counts_by_scene[sc].get(algo, 0)
            print(f"{algo:22s} | {sc:10s} : {c}")
        print("-" * 50)

    # ===== 为每个场景画一张 boxplot =====
    for sc in SCENES:
        plt.figure(figsize=(10, 5))

        rmse_lists = []
        labels = []

        for algo in method_names:
            vals = data_by_scene[sc].get(algo, None)
            if vals is None or len(vals) == 0:
                continue
            rmse_lists.append(vals)
            labels.append(algo)

        if not rmse_lists:
            print(f"[提示] 场景 {sc} 没有任何算法有数据，跳过绘图。")
            plt.close()
            continue

        plt.boxplot(rmse_lists, labels=labels, showmeans=True)
        plt.ylabel("RMSE")
        plt.title(f"Monocular RMSE distribution by method on '{sc}' scenes")
        plt.xticks(rotation=45, ha="right")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
