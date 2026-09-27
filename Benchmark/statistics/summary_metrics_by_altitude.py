#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Summarize SLAM experiment metrics by altitude.

Expected directory layout:
Utilities/paper/
├── summary_metrics_by_altitude.py   <- put this script here
└── experiment_data/
    ├── DROID-SLAM/
    │   ├── mono_metrics.csv
    │   └── rgbd_metrics.csv
    ├── hierslam/
    │   ├── rgbd_metrics.csv
    │   └── semantic_metrics.csv
    ├── MASt3R-SLAM/
    │   ├── calib_metrics.csv
    │   └── nocalib_metrics.csv
    └── ...

For every method folder, this script creates:
    summary_metrics_by_altitude.csv

Output columns:
    altitude,
    SR,
    FPS_mean,
    FPS_std,
    runtime_mean,
    runtime_std,
    PeakReservedGB_mean,
    PeakReservedGB_std,
    rmse_mean,
    rmse_std

Altitude parsing rule:
    dataset names must contain TWO tokens from {high, medium, low}.
    The first token is speed:
        high=8m/s, medium=4m/s, low=2m/s
    The second token is altitude:
        high=30m, medium=20m, low=10m

Examples:
    cross_building_high_low_1     -> speed=high, altitude=10m
    houses_medium_medium_2        -> speed=medium, altitude=20m
    road2_low_high_3              -> speed=low, altitude=30m

Special case:
    MASt3R-SLAM/calib_metrics.csv   -> 10m_mono_calib, ...
    MASt3R-SLAM/nocalib_metrics.csv -> 10m_mono_nocalib, ...

For ordinary files:
    mono_metrics.csv     -> 10m_mono, 20m_mono, 30m_mono
    rgbd_metrics.csv     -> 10m_rgbd, 20m_rgbd, 30m_rgbd
    semantic_metrics.csv -> 10m_semantic, 20m_semantic, 30m_semantic

SR definition:
    valid RMSE rows / all attempted rows in that altitude+modality group.

Rows whose dataset name does not contain at least two high/medium/low tokens
are ignored, e.g. building25fps_1.
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

OUTPUT_NAME = "summary_metrics_by_altitude.csv"

ALTITUDE_MAP = {
    "low": "10m",
    "medium": "20m",
    "high": "30m",
}

ALTITUDE_ORDER = {
    "10m": 0,
    "20m": 1,
    "30m": 2,
}

OUTPUT_COLUMNS = [
    "altitude",
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

# Only these raw metric CSVs are considered.
# Existing summary CSVs and unrelated CSV files will not be read.
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

def extract_altitude(dataset_name: str) -> str | None:
    """
    Extract altitude from dataset name.

    We intentionally use the SECOND occurrence of high/medium/low:
        first  = speed
        second = altitude

    Returns:
        "10m", "20m", "30m", or None if the naming rule is not satisfied.
    """
    tokens = re.findall(
        r"(?<![A-Za-z0-9])(high|medium|low)(?![A-Za-z0-9])",
        str(dataset_name).lower(),
    )

    if len(tokens) < 2:
        return None

    altitude_token = tokens[1]
    return ALTITUDE_MAP[altitude_token]


def to_numeric_clean(series: pd.Series) -> pd.Series:
    """
    Convert a Series to numeric while treating common failure markers
    and +/-inf as NaN.
    """
    s = pd.to_numeric(series, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan)
    return s


def sample_std(series: pd.Series) -> float:
    """
    Sample standard deviation (ddof=1), matching pandas' default std().
    Returns 0.0 when only one valid observation exists.
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


def infer_mode(method_name: str, filename: str) -> str | None:
    """
    Convert an input filename to the label used in the output altitude column.
    """
    lower_method = method_name.lower()
    lower_file = filename.lower()

    if lower_method == "mast3r-slam":
        return MASTR_INPUTS.get(lower_file)

    return NORMAL_INPUTS.get(lower_file)


def discover_metric_files(method_dir: Path) -> list[tuple[Path, str]]:
    """
    Return:
        [(csv_path, mode_label), ...]
    """

    method_name = method_dir.name.lower()
    files = []

    # --------------------------------------------------
    # MASt3R-SLAM
    # --------------------------------------------------
    if method_name == "mast3r-slam":
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

        # 500-frame RGB-D
        rgbd_500 = method_dir / "rgbd_metrics.csv"
        if rgbd_500.is_file():
            files.append((rgbd_500, "rgbd_500"))

        # 500-frame semantic
        semantic_500 = method_dir / "semantic_metrics.csv"
        if semantic_500.is_file():
            files.append((semantic_500, "semantic_500"))

        # Whole-trajectory RGB-D
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
    normal_inputs = {
        "mono_metrics.csv": "mono",
        "rgbd_metrics.csv": "rgbd",
        "semantic_metrics.csv": "semantic",
    }

    for filename, mode in normal_inputs.items():
        csv_path = method_dir / filename

        if csv_path.is_file():
            files.append((csv_path, mode))

    return files


def summarize_one_file(csv_path: Path, mode: str, method_name: str) -> pd.DataFrame:
    """
    Summarize one raw metrics CSV by altitude.
    """
    df = pd.read_csv(csv_path)

    if "dataset" not in df.columns:
        raise ValueError(f"{csv_path}: missing required column 'dataset'")

    # Only datasets containing both speed and altitude keywords are retained.
    df["_altitude"] = df["dataset"].map(extract_altitude)
    df = df[df["_altitude"].notna()].copy()

    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Make expected metric columns numeric when present.
    for col in ["FPS", "runtime", "PeakReservedGB", "rmse"]:
        if col in df.columns:
            df[col] = to_numeric_clean(df[col])

    rows = []

    for altitude in ["10m", "20m", "30m"]:
        g = df[df["_altitude"] == altitude].copy()
        if g.empty:
            continue

        # SR = valid RMSE / all attempted rows in this group.
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
            "altitude": f"{method_name}_{altitude}_{mode}",
            "SR": sr,
            "FPS_mean": mean_value(g["FPS"]) if "FPS" in g.columns else np.nan,
            "FPS_std": sample_std(g["FPS"]) if "FPS" in g.columns else np.nan,
            "runtime_mean": mean_value(g["runtime"]) if "runtime" in g.columns else np.nan,
            "runtime_std": sample_std(g["runtime"]) if "runtime" in g.columns else np.nan,
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
            "rmse_mean": mean_value(g["rmse"]) if "rmse" in g.columns else np.nan,
            "rmse_std": sample_std(g["rmse"]) if "rmse" in g.columns else np.nan,
        }
        rows.append(row)

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def sort_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    parsed = df["altitude"].str.extract(
        r"^(.+)_(10m|20m|30m)_(.+)$"
    )

    df = df.copy()

    df["_method"] = parsed[0]
    df["_height"] = parsed[1]
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

    df["_height_order"] = (
        df["_height"]
        .map(ALTITUDE_ORDER)
        .fillna(999)
    )

    df = (
        df.sort_values(
            [
                "_mode_order",
                "_mode",
                "_height_order",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_method",
                "_height",
                "_mode",
                "_mode_order",
                "_height_order",
            ]
        )
        .reset_index(drop=True)
    )

    return df[OUTPUT_COLUMNS]

def process_method(method_dir: Path) -> bool:
    """
    Process one method directory.

    Returns True if an output file was generated.
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
                method_dir.name
            )
        except Exception as exc:
            print(
                f"[ERROR] "
                f"{method_dir.name}/{csv_path.relative_to(method_dir)}: "
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
        print(f"[SKIP] {method_dir.name}: no valid altitude rows")
        return False

    summary = pd.concat(summaries, ignore_index=True)
    summary = sort_summary(summary)

    output_path = method_dir / OUTPUT_NAME

    # Keep enough precision for paper-side processing; spreadsheet software
    # can format displayed decimals later.
    summary.to_csv(output_path, index=False, float_format="%.6f")

    print(f"[OK]   {method_dir.name}: {output_path}")
    return True


def main() -> None:
    if not EXPERIMENT_ROOT.is_dir():
        raise FileNotFoundError(
            f"experiment_data folder not found: {EXPERIMENT_ROOT}\n"
            f"Please put this script under Utilities/paper/."
        )

    method_dirs = sorted(
        p for p in EXPERIMENT_ROOT.iterdir()
        if p.is_dir()
    )

    generated = 0

    for method_dir in method_dirs:
        print(f"\n=== {method_dir.name} ===")
        if process_method(method_dir):
            generated += 1

    print(
        f"\nDone. Generated {generated} "
        f"'{OUTPUT_NAME}' files under {EXPERIMENT_ROOT}."
    )


if __name__ == "__main__":
    main()
