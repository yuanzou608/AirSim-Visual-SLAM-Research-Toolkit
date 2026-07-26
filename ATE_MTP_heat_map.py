# We'll build two heatmaps (Mono and RGB-D) for ATE RMSE from the provided table.
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# from caas_jupyter_tools import display_dataframe_to_user

# Define rows (methods) and columns (sequences)
methods = [
    "ORB-SLAM3",
    "Photo-SLAM",
    "Droid-SLAM",
    "DPVO",
    "TartanVO",
    "MonoGS",
    "SplaTAM",
    "Hier-SLAM (no semantic)",
    "Hier-SLAM (semantic flat)",
    "MASt3R-SLAM (no calib)",
    "MASt3R-SLAM (has calib)",
    "VGGT-SLAM (no calib)",
    "VGGT-LONG (no calib)",
]

sequences = ["Road", "Building", "Roundabout", "Roundabout_square"]

# Fill ATE RMSE values for Mono and RGB-D; use np.nan for NAs
mono_ate = pd.DataFrame(index=methods, columns=sequences, dtype=float)

mono_ate.loc["ORB-SLAM3"] = [0.22, 1.082, 0.194, 0.184]
mono_ate.loc["Photo-SLAM"] = [0.254, 0.732, 0.221, 0.141]
mono_ate.loc["Droid-SLAM"] = [0.074, 0.37, 0.084, 0.148]
mono_ate.loc["DPVO"] = [0.071, 0.554, 0.139, 0.195]
mono_ate.loc["TartanVO"] = [34.341, 40.452, 21.168, 7.256]
mono_ate.loc["MonoGS"] = [9.166, 74.569, 19.816, 7.886]
mono_ate.loc["SplaTAM"] = [np.nan, np.nan, np.nan, np.nan]
mono_ate.loc["Hier-SLAM (no semantic)"] = [np.nan, np.nan, np.nan, np.nan]
mono_ate.loc["Hier-SLAM (semantic flat)"] = [np.nan, np.nan, np.nan, np.nan]
mono_ate.loc["MASt3R-SLAM (no calib)"] = [2.649, 13.324, 6.139, 3.142]
mono_ate.loc["MASt3R-SLAM (has calib)"] = [0.775, 2.685, 0.291, 0.687]
mono_ate.loc["VGGT-SLAM (no calib)"] = [61.401, 71.722, 4.274, 27.329]
mono_ate.loc["VGGT-LONG (no calib)"] = [24.957, 63.436, 23.708, 18.605]

rgbd_ate = pd.DataFrame(index=methods, columns=sequences, dtype=float)

rgbd_ate.loc["ORB-SLAM3"] = [0.189, 0.999, 0.217, 0.135]
rgbd_ate.loc["Photo-SLAM"] = [0.277, 2.433, 0.216, 0.128]
rgbd_ate.loc["Droid-SLAM"] = [0.229, 0.833, 0.542, 1.137]
rgbd_ate.loc["DPVO"] = [np.nan, np.nan, np.nan, np.nan]
rgbd_ate.loc["TartanVO"] = [np.nan, np.nan, np.nan, np.nan]
rgbd_ate.loc["MonoGS"] = [44.501, 60.467, 21.524, 9.499]
rgbd_ate.loc["SplaTAM"] = [5.558, 30.095, 4.216, 4.372]
rgbd_ate.loc["Hier-SLAM (no semantic)"] = [8.579, 107.345, 17.105, 79.63]
rgbd_ate.loc["Hier-SLAM (semantic flat)"] = [8.609, 79.796, 17.111, 70.203]
rgbd_ate.loc["MASt3R-SLAM (no calib)"] = [np.nan, np.nan, np.nan, np.nan]
rgbd_ate.loc["MASt3R-SLAM (has calib)"] = [np.nan, np.nan, np.nan, np.nan]
rgbd_ate.loc["VGGT-SLAM (no calib)"] = [np.nan, np.nan, np.nan, np.nan]
rgbd_ate.loc["VGGT-LONG (no calib)"] = [np.nan, np.nan, np.nan, np.nan]

# # Show the dataframes in an interactive table for verification
# display_dataframe_to_user("ATE RMSE (Mono)", mono_ate)
# display_dataframe_to_user("ATE RMSE (RGB-D)", rgbd_ate)

# Create heatmap function using matplotlib only, with default colormap and no subplots
# Generate log-scaled heatmaps for ATE RMSE (Mono and RGB-D)

# Compute MTP (Memory-Time Product) = mean(M_i * T_i), with memory in GB and excluding NAs
# We use the previously defined mono_ate, rgbd_ate as a template to align methods/sequences
# We'll now define Peak VRAM (MB) and Runtime (s) values for both Mono and RGB-D, then compute MTP

# Define Peak VRAM (MB) and Runtime (s) for Mono and RGB-D
methods = mono_ate.index.tolist()
sequences = mono_ate.columns.tolist()

vram_mono = pd.DataFrame(index=methods, columns=sequences, dtype=float)
runtime_mono = pd.DataFrame(index=methods, columns=sequences, dtype=float)

vram_rgbd = pd.DataFrame(index=methods, columns=sequences, dtype=float)
runtime_rgbd = pd.DataFrame(index=methods, columns=sequences, dtype=float)

# Fill in from table (in MB)
vram_mono.loc["ORB-SLAM3"] = [782.5, 1119.2, 905, 869]
runtime_mono.loc["ORB-SLAM3"] = [67.43, 107.98, 150.32, 115.22]

vram_mono.loc["Photo-SLAM"] = [1913.86, 4280.9, 2570.77, 2336.82]
runtime_mono.loc["Photo-SLAM"] = [74.48, 207.74, 157.09, 121.01]

vram_mono.loc["Droid-SLAM"] = [14527, 16789.8, 14619.2, 14619.2]
runtime_mono.loc["Droid-SLAM"] = [41.2, 104.38, 65.43, 52.06]

vram_mono.loc["DPVO"] = [2129.92, 2129.92, 2129.92, 2129.92]
runtime_mono.loc["DPVO"] = [29.84, 77.52, 40.77, 54.1]

vram_mono.loc["TartanVO"] = [331.776, 331.776, 331.78, 331.78]
runtime_mono.loc["TartanVO"] = [66.02, 159.571, 113.97, 88.46]

vram_mono.loc["MonoGS"] = [np.nan, np.nan, np.nan, np.nan]
runtime_mono.loc["MonoGS"] = [592.98, 1528.15, 1082.7, 928.76]

vram_mono.loc["SplaTAM"] = [np.nan, np.nan, np.nan, np.nan]
runtime_mono.loc["SplaTAM"] = [np.nan, np.nan, np.nan, np.nan]

vram_mono.loc["Hier-SLAM (no semantic)"] = [np.nan, np.nan, np.nan, np.nan]
runtime_mono.loc["Hier-SLAM (no semantic)"] = [np.nan, np.nan, np.nan, np.nan]

vram_mono.loc["Hier-SLAM (semantic flat)"] = [np.nan, np.nan, np.nan, np.nan]
runtime_mono.loc["Hier-SLAM (semantic flat)"] = [np.nan, np.nan, np.nan, np.nan]

vram_mono.loc["MASt3R-SLAM (no calib)"] = [11509.76, 31579.52, 11939.84, 11929.6]
runtime_mono.loc["MASt3R-SLAM (no calib)"] = [112.52, 310.12, 188.81, 150.25]

vram_mono.loc["MASt3R-SLAM (has calib)"] = [11868.16, 31689.76, 12617.728, 11960.32]
runtime_mono.loc["MASt3R-SLAM (has calib)"] = [116.31, 334.87, 190.16, 154.01]

vram_mono.loc["VGGT-SLAM (no calib)"] = [16209.92, 17192.96, 17162.24, 17162.24]
runtime_mono.loc["VGGT-SLAM (no calib)"] = [23.12, 35.71, 27.72, 24.23]

vram_mono.loc["VGGT-LONG (no calib)"] = [24872.76, 24872.76, 24872.96, 24872.96]
runtime_mono.loc["VGGT-LONG (no calib)"] = [722.35, 1902.57, 1253.4, 893.16]

# RGB-D values
vram_rgbd.loc["ORB-SLAM3"] = [715.6, 912, 793.4, 745]
runtime_rgbd.loc["ORB-SLAM3"] = [82.25, 108.51, 164.27, 130.05]

vram_rgbd.loc["Photo-SLAM"] = [1354.22, 3072.85, 1127.25, 1056.04]
runtime_rgbd.loc["Photo-SLAM"] = [85.32, 216.31, 171.36, 127.91]

vram_rgbd.loc["Droid-SLAM"] = [14342.4, 16789.8, 14711.5, 14619.2]
runtime_rgbd.loc["Droid-SLAM"] = [51.12, 132.83, 83.07, 65.92]

vram_rgbd.loc["DPVO"] = [np.nan, np.nan, np.nan, np.nan]
runtime_rgbd.loc["DPVO"] = [np.nan, np.nan, np.nan, np.nan]

vram_rgbd.loc["TartanVO"] = [np.nan, np.nan, np.nan, np.nan]
runtime_rgbd.loc["TartanVO"] = [np.nan, np.nan, np.nan, np.nan]

vram_rgbd.loc["MonoGS"] = [np.nan, 15179.78, np.nan, 15534.08]
runtime_rgbd.loc["MonoGS"] = [1097.97, 2910.4, 2529.14, 2002.62]

vram_rgbd.loc["SplaTAM"] = [2554, 10648, 3816, 3208]
runtime_rgbd.loc["SplaTAM"] = [2974.44, 9476.2, 6856.2, 5365.86]

vram_rgbd.loc["Hier-SLAM (no semantic)"] = [3722, 15372, 3904, 3772]
runtime_rgbd.loc["Hier-SLAM (no semantic)"] = [814.46, 3800.43, 3313.96, 3313.96]

vram_rgbd.loc["Hier-SLAM (semantic flat)"] = [12824, 18766, 8958, 13636]
runtime_rgbd.loc["Hier-SLAM (semantic flat)"] = [1527.63, 1306.85, 2404.62, 2749.12]

# MASt3R/VGGT variants NA in RGB-D
vram_rgbd.loc["MASt3R-SLAM (no calib)"] = [np.nan]*4
runtime_rgbd.loc["MASt3R-SLAM (no calib)"] = [np.nan]*4
vram_rgbd.loc["MASt3R-SLAM (has calib)"] = [np.nan]*4
runtime_rgbd.loc["MASt3R-SLAM (has calib)"] = [np.nan]*4
vram_rgbd.loc["VGGT-SLAM (no calib)"] = [np.nan]*4
runtime_rgbd.loc["VGGT-SLAM (no calib)"] = [np.nan]*4
vram_rgbd.loc["VGGT-LONG (no calib)"] = [np.nan]*4
runtime_rgbd.loc["VGGT-LONG (no calib)"] = [np.nan]*4

# Convert VRAM MB -> GB
vram_mono /= 1024
vram_rgbd /= 1024

# Compute MTP = mean(M_i * T_i) ignoring NaNs
mtp_mono = (vram_mono * runtime_mono).mean(axis=1, skipna=True)
mtp_rgbd = (vram_rgbd * runtime_rgbd).mean(axis=1, skipna=True)

mtp_mono_df = pd.DataFrame(mtp_mono, columns=["MTP (GB*s)"])
mtp_rgbd_df = pd.DataFrame(mtp_rgbd, columns=["MTP (GB*s)"])




def make_log_heatmap(df: pd.DataFrame, title: str, out_path: str):
    # Compute log10 of ATE values, ignoring NaNs and zeros
    data = df.values.astype(float)
    data_log = np.where(np.isnan(data) | (data <= 0), np.nan, np.log10(data))
    mask = np.isnan(data_log)
    data_filled = np.nan_to_num(data_log, nan=0.0)

    fig, ax = plt.subplots(figsize=(10, max(5, 0.45 * len(df.index))))
    im = ax.imshow(data_filled, aspect="auto", cmap="viridis")
    ax.set_xticks(np.arange(len(df.columns)))
    ax.set_yticks(np.arange(len(df.index)))
    ax.set_xticklabels(df.columns, rotation=30, ha="right")
    ax.set_yticklabels(df.index)
    ax.set_title(title + " (log10 scale)")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("log10(ATE RMSE [m])")

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if not mask[i, j]:
                ax.text(j, i, f"{data_log[i, j]:.2f}", ha="center", va="center", fontsize=8)
            else:
                ax.text(j, i, "NA", ha="center", va="center", fontsize=7, alpha=0.6)

    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


log_mono_path = "ATE_heatmap_mono_log.png"
log_rgbd_path = "ATE_heatmap_rgbd_log.png"

make_log_heatmap(mono_ate, "ATE RMSE Heatmap — Mono", log_mono_path)
make_log_heatmap(rgbd_ate, "ATE RMSE Heatmap — RGB-D", log_rgbd_path)

log_mono_path, log_rgbd_path


# Generate log-scaled heatmaps for MTP (Memory-Time Product)

def make_log_mtp_heatmap(df, title, out_path):
    data = df.values.flatten().astype(float)
    data_log = np.where(np.isnan(data) | (data <= 0), np.nan, np.log10(data))
    mask = np.isnan(data_log)
    data_filled = np.nan_to_num(data_log, nan=0.0)
    
    fig, ax = plt.subplots(figsize=(6, max(5, 0.4 * len(df))))
    im = ax.imshow(data_filled.reshape(-1, 1), aspect="auto", cmap="viridis")
    ax.set_yticks(np.arange(len(df.index)))
    ax.set_yticklabels(df.index)
    ax.set_xticks([0])
    ax.set_xticklabels(["log10(MTP [GB·s])"])
    plt.colorbar(im, ax=ax, label="log10(MTP [GB·s])")
    
    for i, val in enumerate(data_log):
        if not np.isnan(val):
            ax.text(0, i, f"{val:.2f}", ha="center", va="center", fontsize=8)
        else:
            ax.text(0, i, "NA", ha="center", va="center", fontsize=7, alpha=0.6)
    
    plt.title(title + " (log scale)")
    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

log_mono_mtp_path = "MTP_heatmap_mono_log.png"
log_rgbd_mtp_path = "MTP_heatmap_rgbd_log.png"

make_log_mtp_heatmap(mtp_mono_df, "MTP Heatmap — Mono", log_mono_mtp_path)
make_log_mtp_heatmap(mtp_rgbd_df, "MTP Heatmap — RGB-D", log_rgbd_mtp_path)

log_mono_mtp_path, log_rgbd_mtp_path


# Combine Mono and RGB-D MTP (log scale) into one side-by-side heatmap
def make_combined_log_mtp_heatmap(df_mono, df_rgbd, out_path):
    data_mono = np.where(df_mono.values <= 0, np.nan, np.log10(df_mono.values))
    data_rgbd = np.where(df_rgbd.values <= 0, np.nan, np.log10(df_rgbd.values))
    
    data_combined = np.hstack([data_mono, data_rgbd])
    mask = np.isnan(data_combined)
    data_filled = np.nan_to_num(data_combined, nan=0.0)
    
    fig, ax = plt.subplots(figsize=(8, max(5, 0.4 * len(df_mono))))
    im = ax.imshow(data_filled, aspect="auto", cmap="viridis")
    ax.set_yticks(np.arange(len(df_mono.index)))
    ax.set_yticklabels(df_mono.index)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Mono", "RGB-D"])
    plt.colorbar(im, ax=ax, label="log10(MTP [GB·s])")
    
    for i in range(len(df_mono)):
        for j in range(2):
            val = data_combined[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8)
            else:
                ax.text(j, i, "NA", ha="center", va="center", fontsize=7, alpha=0.6)
    
    plt.title("MTP Heatmap (log10 scale) — Mono & RGB-D")
    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

combined_log_mtp_path = "MTP_heatmap_combined_log.png"
make_combined_log_mtp_heatmap(mtp_mono_df, mtp_rgbd_df, combined_log_mtp_path)

combined_log_mtp_path


