#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Combine all method-level summary_metrics_by_altitude.csv files into one table.

Put this script under:
    Utilities/paper/statistics/summary_table_altitude.py

Input files:
    Utilities/paper/experiment_data/<METHOD>/summary_metrics_by_altitude.csv

Output:
    Utilities/paper/statistics/summary_table_altitude.csv

The script preserves the row names already written in each method-level
summary file, for example:
    DPVO_10m_mono
    DROID-SLAM_20m_rgbd
    MASt3R-SLAM_30m_mono_calib
    hierslam_10m_rgbd_500
    hierslam_20m_rgbd_whole
    ...

No additional renaming is performed.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PAPER_DIR = SCRIPT_DIR.parent
EXPERIMENT_ROOT = PAPER_DIR / "experiment_data"

INPUT_NAME = "summary_metrics_by_altitude.csv"
OUTPUT_PATH = SCRIPT_DIR / "summary_table_altitude.csv"

EXPECTED_COLUMNS = [
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

ALTITUDE_ORDER = {
    "10m": 0,
    "20m": 1,
    "30m": 2,
}


def validate_columns(df: pd.DataFrame, csv_path: Path) -> None:
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{csv_path} is missing columns: {missing}"
        )


def extract_method_and_altitude(label: str) -> tuple[str, str]:
    """
    Parse labels such as:
        DPVO_10m_mono
        MASt3R-SLAM_20m_mono_calib
        hierslam_30m_rgbd_whole

    Returns:
        (method_name, altitude)
    """
    text = str(label)

    for altitude in ("10m", "20m", "30m"):
        token = f"_{altitude}_"
        if token in text:
            method = text.split(token, 1)[0]
            return method, altitude

    return text, ""


def main() -> None:
    if not EXPERIMENT_ROOT.is_dir():
        raise FileNotFoundError(
            f"experiment_data folder not found: {EXPERIMENT_ROOT}"
        )

    all_tables = []
    loaded_files = []

    method_dirs = sorted(
        p for p in EXPERIMENT_ROOT.iterdir()
        if p.is_dir()
    )

    for method_dir in method_dirs:
        csv_path = method_dir / INPUT_NAME

        if not csv_path.is_file():
            print(f"[SKIP] {method_dir.name}: {INPUT_NAME} not found")
            continue

        try:
            df = pd.read_csv(csv_path)
            validate_columns(df, csv_path)
        except Exception as exc:
            print(f"[ERROR] {csv_path}: {exc}")
            continue

        # Keep exactly the expected columns and original values.
        df = df[EXPECTED_COLUMNS].copy()

        all_tables.append(df)
        loaded_files.append(csv_path)

        print(
            f"[OK]   {method_dir.name:<20} "
            f"rows={len(df):<3} "
            f"{csv_path}"
        )

    if not all_tables:
        raise RuntimeError(
            f"No valid {INPUT_NAME} files were found under "
            f"{EXPERIMENT_ROOT}"
        )

    summary = pd.concat(
        all_tables,
        ignore_index=True,
    )

    # Sort by method name, then altitude, while preserving different
    # modalities/modes within the same altitude.
    parsed = summary["altitude"].map(extract_method_and_altitude)
    summary["_method"] = parsed.map(lambda x: x[0])
    summary["_altitude_value"] = parsed.map(lambda x: x[1])
    summary["_altitude_order"] = (
        summary["_altitude_value"]
        .map(ALTITUDE_ORDER)
        .fillna(999)
    )

    summary["_original_order"] = range(len(summary))

    summary = (
        summary.sort_values(
            [
                "_method",
                "_altitude_order",
                "_original_order",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_method",
                "_altitude_value",
                "_altitude_order",
                "_original_order",
            ]
        )
        .reset_index(drop=True)
    )

    summary.to_csv(
        OUTPUT_PATH,
        index=False,
        float_format="%.6f",
    )

    print(
        f"\nDone. Combined {len(loaded_files)} method files "
        f"with {len(summary)} total rows."
    )
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
