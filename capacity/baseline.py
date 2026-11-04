"""Baseline workload calculator from historical C1-shaped metrics.

Returns CPU cost per 100 requests/min, network consumption per request,
storage growth estimates, and representative instance-level statistics.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "timestamp",
    "instance_id",
    "instance_type",
    "requests_per_min",
    "avg_latency_ms",
    "p95_latency_ms",
    "cpu_pct",
    "mem_pct",
    "net_in_kb",
    "net_out_kb",
    "disk_used_gb",
    "workload_pattern",
]


def _validate_metrics_df(df: pd.DataFrame) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")
    if df.empty:
        raise ValueError("Input metrics DataFrame is empty.")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def baseline(metrics_df: pd.DataFrame) -> dict:
    """Calculate baseline workload estimates from historical metrics.

    Args:
        metrics_df: Pandas DataFrame with C1 metric columns.

    Returns:
        Dictionary with:
        - cpu_pct_per_100_rpm (median robust estimate)
        - kb_per_request (median network traffic per request)
        - storage_growth_gb_per_day (median per-instance growth, or None)
        - current_disk_used_gb (latest median or mean disk usage)
        - latest_instance_type (most recent observed type)
        - instance_count_latest (number of unique instances in latest timestamp)
        - avg_latency_ms (median observed average latency)
        - p95_latency_ms (median observed p95 latency)
        - per_instance_type_capacity (optional provisional capacities when measured)
    """
    _validate_metrics_df(metrics_df)

    # Work with a copy to avoid mutating input
    df = metrics_df.copy()
    # Ensure numeric columns exist; coerce errors to NaN
    numeric_cols = [
        "requests_per_min",
        "cpu_pct",
        "net_in_kb",
        "net_out_kb",
        "disk_used_gb",
        "avg_latency_ms",
        "p95_latency_ms",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter valid observations: positive request rate, finite numeric values
    valid_mask = (
        df["requests_per_min"].notna()
        & (df["requests_per_min"] > 0)
        & df["cpu_pct"].notna()
        & df["net_in_kb"].notna()
        & df["net_out_kb"].notna()
        & df["disk_used_gb"].notna()
        & (df["cpu_pct"] >= 0)
        & df["cpu_pct"].apply(lambda x: math.isfinite(x) if pd.notna(x) else False)
    )
    valid_df = df[valid_mask].copy()

    if valid_df.empty:
        raise ValueError(
            "No valid observations after filtering (positive requests_per_min, finite values)."
        )

    # 6.1 CPU consumption per 100 requests/minute
    # Formula: cpu_pct * 100 / requests_per_min
    valid_df["cpu_pct_per_100_rpm"] = valid_df["cpu_pct"] * 100.0 / valid_df["requests_per_min"]
    cpu_pct_per_100_rpm = float(valid_df["cpu_pct_per_100_rpm"].median())
    if not math.isfinite(cpu_pct_per_100_rpm) or cpu_pct_per_100_rpm < 0:
        raise ValueError(f"Computed CPU coefficient is invalid: {cpu_pct_per_100_rpm}")

    # 6.2 Network consumption per request
    # Validate columns represent per-minute traffic (not cumulative counters).
    # For this implementation we assume the given values are per-minute traffic.
    # If they were cumulative counters, interval deltas would be needed.
    valid_df["kb_per_request"] = (
        valid_df["net_in_kb"] + valid_df["net_out_kb"]
    ) / valid_df["requests_per_min"]
    kb_per_request = float(valid_df["kb_per_request"].median())
    if not math.isfinite(kb_per_request) or kb_per_request < 0:
        raise ValueError(f"Computed network consumption is invalid: {kb_per_request}")

    # 6.3 Storage growth per day
    # Process chronologically per instance; calculate slope of disk_used_gb vs time.
    storage_growth = None
    if "timestamp" in df.columns:
        df["timestamp_parsed"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Drop rows with unparseable timestamps
        time_df = df.dropna(subset=["timestamp_parsed", "disk_used_gb"])
        if not time_df.empty:
            growths = []
            for inst_id, group in time_df.groupby("instance_id"):
                group_sorted = group.sort_values("timestamp_parsed")
                # Need at least two observations to estimate a trend
                if len(group_sorted) >= 2:
                    # Convert to numeric timestamps (days since first observation)
                    first_ts = group_sorted["timestamp_parsed"].min()
                    days = (group_sorted["timestamp_parsed"] - first_ts).dt.total_seconds() / 86400.0
                    disk = group_sorted["disk_used_gb"]
                    # Require at least some positive time span
                    positive_days = days[days > 0]
                    if len(positive_days) >= 1:
                        # Simple linear regression slope using numpy polyfit
                        try:
                            coeffs = pd.Series(disk.values).astype(float).to_numpy()
                            days_np = days.values.astype(float)
                            # Filter finite pairs
                            finite_mask = (
                                pd.notna(coeffs) & (coeffs == coeffs) & pd.notna(days_np) & (days_np == days_np)
                            )
                            if finite_mask.sum() >= 2:
                                slope, _ = _linregress(days_np[finite_mask], coeffs[finite_mask])
                                if math.isfinite(slope) and slope >= -1e-6:  # allow very small negative noise
                                    growths.append(slope)
                        except Exception:
                            # If regression fails, skip this instance quietly
                            pass
            if growths:
                storage_growth = float(pd.Series(growths).median())
                if storage_growth < 0 and storage_growth > -1e-6:
                    storage_growth = 0.0  # Clamp near-zero negative noise
    # If insufficient history, explicitly keep None
    storage_result: Optional[float] = storage_growth

    # 6.4 Additional useful baseline information
    # Latest instance type (most frequent in latest timestamp group)
    latest_ts = df["timestamp_parsed"].max() if "timestamp_parsed" in df.columns else None
    latest_instance_type: Optional[str] = None
    instance_count_latest: int = 0
    if latest_ts is not None and pd.notna(latest_ts):
        latest_df = df[df["timestamp_parsed"] == latest_ts]
        if not latest_df.empty:
            instance_count_latest = int(latest_df["instance_id"].nunique())
            latest_instance_type = (
                latest_df["instance_type"].mode()
            )
            if len(latest_instance_type) > 0:
                latest_instance_type = str(latest_instance_type.iloc[0])

    current_disk_used_gb: Optional[float] = None
    if "disk_used_gb" in df.columns:
        latest_disk = df.groupby("instance_id")["disk_used_gb"].last()
        if not latest_disk.empty:
            current_disk_used_gb = float(latest_disk.median())

    avg_latency_ms: Optional[float] = (
        float(valid_df["avg_latency_ms"].median()) if not valid_df.empty else None
    )
    p95_latency_ms_result: Optional[float] = (
        float(valid_df["p95_latency_ms"].median()) if not valid_df.empty else None
    )

    # Per-instance-type capacity measurements (provisional if available)
    per_instance_type_capacity = {}
    # When actual measurements exist (e.g., from Member 1), we would populate
    # based on measured requests handled per instance type. For Phase II,
    # we return an empty dict or note that measurements are unavailable.

    result = {
        "cpu_pct_per_100_rpm": cpu_pct_per_100_rpm,
        "kb_per_request": kb_per_request,
        "storage_growth_gb_per_day": storage_result,
        "current_disk_used_gb": current_disk_used_gb,
        "latest_instance_type": latest_instance_type,
        "instance_count_latest": instance_count_latest,
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms_result,
        "per_instance_type_capacity": per_instance_type_capacity,
        "notes": {
            "cpu_pct_per_100_rpm": "Median robust estimate. Linear approximation only; workload may become nonlinear near saturation.",
            "kb_per_request": "Median network traffic per request (net_in_kb + net_out_kb) / requests_per_min. Units: decimal KB per request.",
            "storage_growth_gb_per_day": "Median linear growth slope (GB/day) across instances with sufficient history; None when history is insufficient.",
            "network_unit_note": "net_in_kb and net_out_kb are treated as per-minute traffic values (not cumulative counters). If they are cumulative, interval deltas must be computed first.",
        },
    }
    return result


def _linregress(x: pd.Series, y: pd.Series) -> tuple:
    """Simple linear regression returning (slope, intercept)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    coeffs = np.polyfit(x_arr, y_arr, 1)
    return float(coeffs[0]), float(coeffs[1])
