#!/usr/bin/env python3
"""Demonstrate the capacity engine at 500 and 5,000 requests/minute.

Uses synthetic C1-shaped data, a synthetic C2 forecast, and the cached
pricing.json (test-only fixtures clearly identified).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

from capacity import baseline, plan, plan_for_rpm, pricing


def make_synthetic_metrics_df(rows_per_instance: int = 10) -> pd.DataFrame:
    """Generate synthetic C1-shaped metrics for demonstration only."""
    timestamps = pd.date_range(start="2026-10-25T10:00:00Z", periods=rows_per_instance, freq="min", tz="UTC")
    records = []
    for i in range(2):  # 2 instances
        for ts in timestamps:
            # Vary requests slightly to create realistic variance
            rpm = 500 + np.random.randint(-50, 51) if rows_per_instance > 3 else 500
            records.append({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "instance_id": f"i-{i+1:02d}",
                "instance_type": "t3.micro",
                "requests_per_min": float(rpm),
                "avg_latency_ms": float(40 + np.random.randint(-5, 6)),
                "p95_latency_ms": float(85 + np.random.randint(-5, 6)),
                "cpu_pct": float(30 + np.random.randint(0, 10)),
                "mem_pct": float(50 + np.random.randint(-5, 6)),
                "net_in_kb": float(700 + np.random.randint(-50, 51)),
                "net_out_kb": float(6000 + np.random.randint(-200, 201)),
                "disk_used_gb": float(3.0 + (i * 0.05)),
                "workload_pattern": "steady",
            })
    return pd.DataFrame(records)


def make_sample_forecast() -> dict:
    return {
        "generated_at": "2026-10-27T10:00:00Z",
        "model": "lstm",
        "horizon_minutes": 1440,
        "step_minutes": 15,
        "accuracy": {"mape_pct": 8.4, "rmse": 42.1},
        "series": [
            {"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 640, "cpu_pct": 41.0, "mem_pct": 55.0, "lower": 590, "upper": 700},
            {"timestamp": "2026-10-25T10:45:00Z", "requests_per_min": 520, "cpu_pct": 36.0, "mem_pct": 53.0, "lower": 480, "upper": 560},
        ],
        "cpu_threshold_pct": 70,
        "exhaustion_at": "2026-10-25T18:45:00Z",
    }


def run_demo():
    print("=" * 70)
    print("MEMBER 3 — CAPACITY AND COST ENGINE DEMONSTRATION")
    print("Synthetic data and provisional assumptions are clearly labelled below.")
    print("=" * 70)

    # Load prices (test fixture)
    try:
        prices = pricing.load_prices()
        print(f"\nLoaded price cache: {len(prices)} instance prices (test fixtures).")
    except Exception as exc:
        print(f"\nWARNING: Could not load prices ({exc}). Using placeholder logic.")
        prices = {}

    # Synthetic baseline
    print("\n--- BASELINE (synthetic C1 data, 2 instances, 10 minutes) ---")
    metrics_df = make_synthetic_metrics_df()
    baseline_result = baseline(metrics_df)
    print(f"cpu_pct_per_100_rpm: {baseline_result.get('cpu_pct_per_100_rpm')}")
    print(f"kb_per_request: {baseline_result.get('kb_per_request')}")
    print(f"storage_growth_gb_per_day: {baseline_result.get('storage_growth_gb_per_day')}")
    print(f"current_disk_used_gb: {baseline_result.get('current_disk_used_gb')}")
    print(f"latest_instance_type: {baseline_result.get('latest_instance_type')}")
    print(f"instance_count_latest: {baseline_result.get('instance_count_latest')}")
    print(f"avg_latency_ms: {baseline_result.get('avg_latency_ms')}")
    print(f"p95_latency_ms: {baseline_result.get('p95_latency_ms')}")
    print("NOTE: All baseline values come from synthetic data, not real AWS metrics.")

    # Demonstrate 500 rpm
    print("\n--- WORKLOAD: 500 requests/min ---")
    forecast_500 = make_sample_forecast()
    # Modify peak to 500 for the demonstration
    plan_500 = plan_for_rpm(forecast=forecast_500, baseline_result=baseline_result, expected_rpm=500.0)
    print(f"Peak RPM: {plan_500['peak_requests_per_min']}")
    for opt in plan_500["options"]:
        print(f"  {opt['strategy']}: {opt['instances']}x {opt['instance_type']} @ ${opt['usd_per_hour']}/hr (${opt['usd_per_day']}/day), latency={opt['expected_latency_ms']}ms, SPOF={opt['single_point_of_failure']}")
    print(f"Recommendation: {plan_500['recommendation']}")
    print(f"Reason: {plan_500['reason']}")
    print(f"Bandwidth: {plan_500['bandwidth_mbps']} Mbps")
    print(f"30-day storage projection: {plan_500['storage_gb_30d']} GB")
    print(f"Exhaustion at: {plan_500['exhaustion_at']}")

    # Demonstrate 5,000 rpm
    print("\n--- WORKLOAD: 5,000 requests/min ---")
    plan_5000 = plan_for_rpm(forecast=forecast_500, baseline_result=baseline_result, expected_rpm=5000.0)
    print(f"Peak RPM: {plan_5000['peak_requests_per_min']}")
    for opt in plan_5000["options"]:
        print(f"  {opt['strategy']}: {opt['instances']}x {opt['instance_type']} @ ${opt['usd_per_hour']}/hr (${opt['usd_per_day']}/day), latency={opt['expected_latency_ms']}ms, SPOF={opt['single_point_of_failure']}")
    print(f"Recommendation: {plan_5000['recommendation']}")
    print(f"Reason: {plan_5000['reason']}")
    print(f"Bandwidth: {plan_5000['bandwidth_mbps']} Mbps")
    print(f"30-day storage projection: {plan_5000['storage_gb_30d']} GB")
    print(f"Exhaustion at: {plan_5000['exhaustion_at']}")

    # Serialise to JSON for verification
    output_path = Path(__file__).resolve().parent.parent / "demo_plan_5000.json"
    with open(output_path, "w") as f:
        json.dump(plan_5000, f, indent=2)
    print(f"\nSerialized 5,000 RPM plan to: {output_path}")

    # Note about latency and capacity assumptions
    print("\n--- ASSUMPTIONS AND LIMITATIONS ---")
    print("Latency estimates are provisional (Phase II simplified estimator).")
    print("Scale-up capacity uses configured provisional multipliers, NOT measured AWS performance.")
    print("Prices come from the cached pricing.json test fixture; live retrieval requires fetch_prices.py.")
    print("Storage growth is estimated by linear regression across synthetic instance observations.")

    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
