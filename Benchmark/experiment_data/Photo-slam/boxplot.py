import os
import pandas as pd
import matplotlib.pyplot as plt


# ========= 配置部分 =========
CSV_NAME = "mono_metrics.csv"   # 如果是 calib_metrics.csv 就改这里
SCENES = ["building", "houses", "pool", "road", "roundabout"]


def get_scene_from_name(dataset_name: str):
    """
    根据数据集名字判断场景类型。
    例子: 'road25fps_1', 'houses_high_low_2', 'cross_building_high_high_3'
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
    csv_path = os.path.join(os.getcwd(), CSV_NAME)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"找不到 {csv_path}，请确认脚本所在目录和 CSV 名称是否正确。")

    df = pd.read_csv(csv_path)

    if "dataset" not in df.columns or "rmse" not in df.columns:
        raise ValueError("CSV 里需要包含 'dataset' 和 'rmse' 两列。")

    # 添加 scene 列
    df["scene"] = df["dataset"].apply(get_scene_from_name)

    # 为每个场景收集 rmse
    rmse_by_scene = []
    counts = {}

    for sc in SCENES:
        rmse_vals = df.loc[df["scene"] == sc, "rmse"].dropna().values
        rmse_by_scene.append(rmse_vals)
        counts[sc] = len(rmse_vals)

    # 打印每个场景的实验数量
    print("\n每个场景的 RMSE 样本数量：")
    for sc in SCENES:
        print(f"{sc:10s}: {counts[sc]}")

    # 只要有至少一个场景有数据就画图
    if any(len(v) > 0 for v in rmse_by_scene):
        plt.figure(figsize=(8, 6))
        plt.boxplot(rmse_by_scene, labels=SCENES, showmeans=True)

        plt.ylabel("RMSE")
        plt.title("RMSE Distribution by Scene(Photo-SLAM)")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        plt.show()
    else:
        print("所有场景的 rmse 都为空，无法绘制箱线图。")


if __name__ == "__main__":
    main()
