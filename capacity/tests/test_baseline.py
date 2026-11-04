import math
import numpy as np
import pandas as pd
import pytest

from capacity import baseline


def test_valid_input_produces_finite_values(sample_metrics_df):
    result = baseline(sample_metrics_df)
    assert math.isfinite(result["cpu_pct_per_100_rpm"])
    assert result["cpu_pct_per_100_rpm"] > 0
    assert math.isfinite(result["kb_per_request"])
    assert result["kb_per_request"] >= 0


def test_zero_request_rate_avoids_division_by_zero():
    df = pd.DataFrame({
        "timestamp": ["2026-10-25T10:00:00Z"],
        "instance_id": ["i-01"],
        "instance_type": ["t3.micro"],
        "requests_per_min": [0.0],
        "avg_latency_ms": [40.0],
        "p95_latency_ms": [85.0],
        "cpu_pct": [30.0],
        "mem_pct": [50.0],
        "net_in_kb": [100.0],
        "net_out_kb": [200.0],
        "disk_used_gb": [3.0],
        "workload_pattern": ["steady"],
    })
    # Zero requests should filter out, leaving no valid observations
    with pytest.raises(ValueError):
        baseline(df)


def test_missing_required_columns():
    df = pd.DataFrame({"timestamp": ["2026-10-25T10:00:00Z"]})
    with pytest.raises(ValueError, match="Missing required columns"):
        baseline(df)


def test_nan_infinite_values_handled():
    df = pd.DataFrame({
        "timestamp": ["2026-10-25T10:00:00Z", "2026-10-25T10:01:00Z"],
        "instance_id": ["i-01", "i-01"],
        "instance_type": ["t3.micro", "t3.micro"],
        "requests_per_min": [500.0, float("nan")],
        "avg_latency_ms": [40.0, 42.0],
        "p95_latency_ms": [85.0, 88.0],
        "cpu_pct": [30.0, float("inf")],
        "mem_pct": [50.0, 52.0],
        "net_in_kb": [100.0, 110.0],
        "net_out_kb": [200.0, 220.0],
        "disk_used_gb": [3.0, 3.1],
        "workload_pattern": ["steady", "steady"],
    })
    result = baseline(df)
    # NaN and inf rows should be excluded
    assert math.isfinite(result["cpu_pct_per_100_rpm"])


def test_empty_dataset_raises():
    df = pd.DataFrame()
    with pytest.raises(ValueError):
        baseline(df)


def test_storage_growth_respects_timestamps():
    df = pd.DataFrame({
        "timestamp": [
            "2026-10-25T10:00:00Z",
            "2026-10-26T10:00:00Z",
        ],
        "instance_id": ["i-01", "i-01"],
        "instance_type": ["t3.micro", "t3.micro"],
        "requests_per_min": [500.0, 500.0],
        "avg_latency_ms": [40.0, 42.0],
        "p95_latency_ms": [85.0, 88.0],
        "cpu_pct": [30.0, 32.0],
        "mem_pct": [50.0, 52.0],
        "net_in_kb": [100.0, 110.0],
        "net_out_kb": [200.0, 220.0],
        "disk_used_gb": [3.0, 3.5],  # 0.5 GB over 1 day
        "workload_pattern": ["steady", "steady"],
    })
    result = baseline(df)
    # Storage growth should be approximately 0.5 GB/day
    assert result["storage_growth_gb_per_day"] is not None
    assert result["storage_growth_gb_per_day"] >= 0.4


def test_network_unit_documented():
    result = baseline(pd.DataFrame({
        "timestamp": ["2026-10-25T10:00:00Z"],
        "instance_id": ["i-01"],
        "instance_type": ["t3.micro"],
        "requests_per_min": [100.0],
        "avg_latency_ms": [40.0],
        "p95_latency_ms": [85.0],
        "cpu_pct": [10.0],
        "mem_pct": [50.0],
        "net_in_kb": [200.0],
        "net_out_kb": [300.0],
        "disk_used_gb": [3.0],
        "workload_pattern": ["steady"],
    }))
    # net_in_kb + net_out_kb = 500 kb; 100 rpm => 5 kb/request
    assert math.isclose(result["kb_per_request"], 5.0, rel_tol=1e-3)
