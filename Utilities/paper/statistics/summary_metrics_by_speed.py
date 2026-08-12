#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Summarize SLAM experiment metrics by speed.

Put this script under:
    Utilities/paper/statistics/summary_metrics_by_speed.py

Experiment data root:
    Utilities/paper/experiment_data/

For every method folder, this script creates:
    summary_metrics_by_speed.csv

Output columns:
    speed,
    SR,
    FPS_mean,
    FPS_std,
    runtime_mean,
    runtime_std,
    PeakReservedGB_mean,
    PeakReservedGB_std,
    rmse_mean,
    rmse_std

Dataset naming rule:
    dataset names must contain TWO tokens from {high, medium, low}.

    The FIRST token is speed:
        high   -> 8m/s
        medium -> 4m/s
        low    -> 2m/s

    The SECOND token is altitude:
        high   -> 30m
        medium -> 20m
        low    -> 10m

Examples:
    cross_building_high_low_1
                   ^    ^
                 speed altitude
        -> speed = 8m/s, altitude = 10m

    houses_medium_medium_2
           ^      ^
         speed  altitude
        -> speed = 4m/s, altitude = 20m

    road2_low_high_3
          ^   ^
        speed altitude
        -> speed = 2m/s, altitude = 30m

Only datasets containing at least two high/medium/low tokens are included.
Rows such as building25fps_1 are ignored.

Special cases:
1. MASt3R-SLAM
    calib_metrics.csv
        -> MASt3R-SLAM_2m/s_mono_calib
        -> MASt3R-SLAM_4m/s_mono_calib
        -> MASt3R-SLAM_8m/s_mono_calib

    nocalib_metrics.csv
        -> MASt3R-SLAM_2m/s_mono_nocalib
        -> ...

2. hierslam
    hierslam/rgbd_metrics.csv
        -> hierslam_2m/s_rgbd_500
        -> ...

    hierslam/semantic_metrics.csv
        -> hierslam_2m/s_semantic_500
        -> ...

    hierslam/rgbd_whole_trajectory/rgbd_metrics.csv
        -> hierslam_2m/s_rgbd_whole
        -> ...

For ordinary files:
    mono_metrics.csv
        -> METHOD_2m/s_mono, METHOD_4m/s_mono, METHOD_8m/s_mono

    rgbd_metrics.csv
        -> METHOD_2m/s_rgbd, METHOD_4m/s_rgbd, METHOD_8m/s_rgbd

    semantic_metrics.csv
        -> METHOD_2m/s_semantic, METHOD_4m/s_semantic, METHOD_8m/s_semantic

SR definition:
    valid RMSE rows / all attempted rows in that speed+modality group.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PAPER_DIR = SCRIPT_DIR.parent
EXPERIMENT_ROOT = PAPER_DIR / "experiment_data"

OUTPUT_NAME = "summary_metrics_by_speed.csv"

SPEED_MAP = {
    "low": "2m/s",
    "medium": "4m/s",
    "high": "8m/s",
}

SPEED_ORDER = {
    "2m/s": 0,
    "4m/s": 1,
    "8m/s": 2,
}

OUTPUT_COLUMNS = [
    "speed",
    "SR",
    "FPS_mean",
    "FPS_std",
    "runtime_mean",
    "runtime_std",
    "PeakReservedGB_mean",
    "PeakReservedGB_std",
    "rmse_mean",
    "rmse_std",
]

NORMAL_INPUTS = {
    "mono_metrics.csv": "mono",
    "rgbd_metrics.csv": "rgbd",
    "semantic_metrics.csv": "semantic",
}

MASTR_INPUTS = {
    "calib_metrics.csv": "mono_calib",
    "nocalib_metrics.csv": "mono_nocalib",
}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def extract_speed(dataset_name: str) -> str | None:
    """
    Extract speed from dataset name.

    The FIRST high/medium/low token is speed:
        low    -> 2m/s
        medium -> 4m/s
        high   -> 8m/s

    The SECOND token is altitude, but it is not used for speed grouping.

    Returns:
        "2m/s", "4m/s", "8m/s", or None.
    """
    tokens = re.findall(
        r"(?<![A-Za-z0-9])(high|medium|low)(?![A-Za-z0-9])",
        str(dataset_name).lower(),
    )

    # Require both speed and altitude tokens so that datasets like
    # building25fps_1 are excluded.
    if len(tokens) < 2:
        return None

    speed_token = tokens[0]
    return SPEED_MAP[speed_token]


def to_numeric_clean(series: pd.Series) -> pd.Series:
    """
    Convert a Series to numeric and treat invalid values / +/-inf as NaN.
    """
    s = pd.to_numeric(series, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan)
    return s


def sample_std(series: pd.Series) -> float:
    """
    Sample standard deviation (ddof=1).
    If only one valid value exists, return 0.0.
    """
    x = to_numeric_clean(series).dropna()

    if len(x) == 0:
        return np.nan

    if len(x) == 1:
        return 0.0

    return float(x.std(ddof=1))


def mean_value(series: pd.Series) -> float:
    x = to_numeric_clean(series).dropna()

    if len(x) == 0:
        return np.nan

    return float(x.mean())


def discover_metric_files(method_dir: Path) -> list[tuple[Path, str]]:
    """
    Discover raw metric files for one method.

    Returns:
        [(csv_path, mode_label), ...]
    """
    method_name = method_dir.name.lower()
    files: list[tuple[Path, str]] = []

    # --------------------------------------------------
    # MASt3R-SLAM special case
    # --------------------------------------------------
    if method_name == "mastr3-slam":
        calib = method_dir / "calib_metrics.csv"
        nocalib = method_dir / "nocalib_metrics.csv"

        if calib.is_file():
            files.append((calib, "mono_calib"))

        if nocalib.is_file():
            files.append((nocalib, "mono_nocalib"))

        return files

    # --------------------------------------------------
    # Hier-SLAM special case
    # --------------------------------------------------
    if method_name == "hierslam":
        # 500-frame RGB-D result
        rgbd_500 = method_dir / "rgbd_metrics.csv"
        if rgbd_500.is_file():
            files.append((rgbd_500, "rgbd_500"))

        # 500-frame semantic result
        semantic_500 = method_dir / "semantic_metrics.csv"
        if semantic_500.is_file():
            files.append((semantic_500, "semantic_500"))

        # Whole-trajectory RGB-D result
        rgbd_whole = (
            method_dir
            / "rgbd_whole_trajectory"
            / "rgbd_metrics.csv"
        )

        if rgbd_whole.is_file():
            files.append((rgbd_whole, "rgbd_whole"))

        return files

    # --------------------------------------------------
    # Normal methods
    # --------------------------------------------------
    for filename, mode in NORMAL_INPUTS.items():
        csv_path = method_dir / filename

        if csv_path.is_file():
            files.append((csv_path, mode))

    return files


def summarize_one_file(
    csv_path: Path,
    mode: str,
    method_name: str,
) -> pd.DataFrame:
    """
    Summarize one raw metrics CSV by speed.
    """
    df = pd.read_csv(csv_path)

    if "dataset" not in df.columns:
        raise ValueError(
            f"{csv_path}: missing required column 'dataset'"
        )

    # Keep only rows satisfying the two-token speed/altitude naming rule.
    df["_speed"] = df["dataset"].map(extract_speed)
    df = df[df["_speed"].notna()].copy()

    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Convert expected metrics to numeric.
    for col in ["FPS", "runtime", "PeakReservedGB", "rmse"]:
        if col in df.columns:
            df[col] = to_numeric_clean(df[col])

    rows = []

    for speed in ["2m/s", "4m/s", "8m/s"]:
        g = df[df["_speed"] == speed].copy()

        if g.empty:
            continue

        # SR = valid RMSE rows / all attempted rows.
        if "rmse" in g.columns:
            valid_rmse = (
                pd.to_numeric(g["rmse"], errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
                .notna()
            )
            sr = float(valid_rmse.sum() / len(g))
        else:
            sr = np.nan

        row = {
            "speed": f"{method_name}_{speed}_{mode}",
            "SR": sr,
            "FPS_mean": (
                mean_value(g["FPS"])
                if "FPS" in g.columns
                else np.nan
            ),
            "FPS_std": (
                sample_std(g["FPS"])
                if "FPS" in g.columns
                else np.nan
            ),
            "runtime_mean": (
                mean_value(g["runtime"])
                if "runtime" in g.columns
                else np.nan
            ),
            "runtime_std": (
                sample_std(g["runtime"])
                if "runtime" in g.columns
                else np.nan
            ),
            "PeakReservedGB_mean": (
                mean_value(g["PeakReservedGB"])
                if "PeakReservedGB" in g.columns
                else np.nan
            ),
            "PeakReservedGB_std": (
                sample_std(g["PeakReservedGB"])
                if "PeakReservedGB" in g.columns
                else np.nan
            ),
            "rmse_mean": (
                mean_value(g["rmse"])
                if "rmse" in g.columns
                else np.nan
            ),
            "rmse_std": (
                sample_std(g["rmse"])
                if "rmse" in g.columns
                else np.nan
            ),
        }

        rows.append(row)

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def sort_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort by modality/mode first, then speed:
        2m/s
        4m/s
        8m/s
    """
    if df.empty:
        return df

    # Method names may contain "-" and other characters, so detect the
    # explicit speed token from the generated label.
    parsed = df["speed"].str.extract(
        r"^(.+)_(2m/s|4m/s|8m/s)_(.+)$"
    )

    df = df.copy()

    df["_method"] = parsed[0]
    df["_speed_value"] = parsed[1]
    df["_mode"] = parsed[2]

    mode_order = {
        "mono": 0,
        "mono_calib": 1,
        "mono_nocalib": 2,

        "rgbd": 3,
        "rgbd_500": 4,
        "rgbd_whole": 5,

        "semantic": 6,
        "semantic_500": 7,
    }

    df["_mode_order"] = (
        df["_mode"]
        .map(mode_order)
        .fillna(999)
    )

    df["_speed_order"] = (
        df["_speed_value"]
        .map(SPEED_ORDER)
        .fillna(999)
    )

    df = (
        df.sort_values(
            [
                "_mode_order",
                "_mode",
                "_speed_order",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_method",
                "_speed_value",
                "_mode",
                "_mode_order",
                "_speed_order",
            ]
        )
        .reset_index(drop=True)
    )

    return df[OUTPUT_COLUMNS]


def process_method(method_dir: Path) -> bool:
    """
    Process one method directory.

    Returns:
        True if summary_metrics_by_speed.csv was generated.
    """
    metric_files = discover_metric_files(method_dir)

    if not metric_files:
        return False

    summaries = []

    for csv_path, mode in metric_files:
        try:
            part = summarize_one_file(
                csv_path,
                mode,
                method_dir.name,
            )

        except Exception as exc:
            print(
                f"[ERROR] "
                f"{method_dir.name}/"
                f"{csv_path.relative_to(method_dir)}: "
                f"{exc}"
            )
            continue

        if not part.empty:
            summaries.append(part)

        print(
            f"  - {str(csv_path.relative_to(method_dir)):<40} "
            f"mode={mode:<16} "
            f"rows={len(part)}"
        )

    if not summaries:
        print(
            f"[SKIP] {method_dir.name}: "
            f"no valid speed rows"
        )
        return False

    summary = pd.concat(
        summaries,
        ignore_index=True,
    )

    summary = sort_summary(summary)

    output_path = method_dir / OUTPUT_NAME

    summary.to_csv(
        output_path,
        index=False,
        float_format="%.6f",
    )

    print(
        f"[OK]   {method_dir.name}: "
        f"{output_path}"
    )

    return True


def main() -> None:
    if not EXPERIMENT_ROOT.is_dir():
        raise FileNotFoundError(
            f"experiment_data folder not found: "
            f"{EXPERIMENT_ROOT}\n"
            f"Please put this script under "
            f"Utilities/paper/statistics/."
        )

    method_dirs = sorted(
        p
        for p in EXPERIMENT_ROOT.iterdir()
        if p.is_dir()
    )

    generated = 0

    for method_dir in method_dirs:
        print(f"\n=== {method_dir.name} ===")

        if process_method(method_dir):
            generated += 1

    print(
        f"\nDone. Generated {generated} "
        f"'{OUTPUT_NAME}' files under "
        f"{EXPERIMENT_ROOT}."
    )


if __name__ == "__main__":
    main()
