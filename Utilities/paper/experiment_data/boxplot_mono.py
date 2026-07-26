import os
import pandas as pd
import matplotlib.pyplot as plt

ROOT = "/home/yuan/SLAM/scripts/paper/experiment_data"

methods = []       # x-axis labels
rmse_lists = []    # RMSE list for each method
counts = {}        # sample count


def load_rmse(csv_path):
    """Load rmse array safely"""
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    if "rmse" not in df.columns:
        return None
    vals = df["rmse"].dropna().values
    if len(vals) == 0:
        return None
    return vals

for name in sorted(os.listdir(ROOT)):
    method_dir = os.path.join(ROOT, name)

    if not os.path.isdir(method_dir):
        continue

    # --- 特殊处理 MASt3R-SLAM ---
    if name.lower() == "mast3r-slam":

        calib_csv    = os.path.join(method_dir, "calib_metrics.csv")
        nocalib_csv  = os.path.join(method_dir, "nocalib_metrics.csv")

        # 读取 calib
        calib_rmse = load_rmse(calib_csv)
        if calib_rmse is not None:
            method_label = "MASt3R-SLAM (calib)"
            methods.append(method_label)
            rmse_lists.append(calib_rmse)
            counts[method_label] = len(calib_rmse)

        # 读取 nocalib
        nocalib_rmse = load_rmse(nocalib_csv)
        if nocalib_rmse is not None:
            method_label = "MASt3R-SLAM (no calib)"
            methods.append(method_label)
            rmse_lists.append(nocalib_rmse)
            counts[method_label] = len(nocalib_rmse)

        continue

    # --- 其他 SLAM 方法默认使用 mono_metrics.csv ---
    csv_path = os.path.join(method_dir, "mono_metrics.csv")
    rmse = load_rmse(csv_path)

    if rmse is None:
        print(f"[跳过] {name}: 没有有效 mono_metrics.csv")
        continue

    methods.append(name)
    rmse_lists.append(rmse)
    counts[name] = len(rmse)

# ===== 打印每个方法有多少条数据 =====
print("\n== RMSE 样本数量 ==")
for m in methods:
    print(f"{m:22s}: {counts[m]}")


# ===== 绘制箱线图 =====
plt.figure(figsize=(14, 6))
plt.boxplot(rmse_lists, labels=methods, showmeans=True)

plt.ylabel("RMSE")
plt.title("RMSE Distribution Across SLAM Methods (mono + MASt3R calib/no-calib)")
plt.xticks(rotation=45, ha="right")
plt.grid(False, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()
