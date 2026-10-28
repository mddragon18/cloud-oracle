"""Module 2 stub: forecast(metrics) -> C2 dict (contracts/README.md).

Naive linear-trend version so everyone can run it until Member 2 replaces it
with ARIMA/LSTM. Pure stdlib — no pandas/statsmodels needed for the stub.
"""
import csv
import json
import math
import os
from datetime import datetime, timedelta, timezone


def load_metrics(path):
    """C1 csv -> list of dicts (numbers converted). Stub for pandas users."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            row = {"timestamp": r["timestamp"], "instance_id": r["instance_id"],
                   "instance_type": r["instance_type"], "workload_pattern": r["workload_pattern"]}
            for k in ("requests_per_min", "avg_latency_ms", "p95_latency_ms", "cpu_pct",
                      "mem_pct", "net_in_kb", "net_out_kb", "disk_used_gb"):
                row[k] = float(r[k])
            rows.append(row)
    return rows


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def forecast(metrics, horizon_minutes=1440, step_minutes=15, cpu_threshold_pct=70.0):
    """metrics: list of C1 row dicts -> C2 dict. Replace with statsmodels ARIMA."""
    if len(metrics) < 2:
        raise ValueError("need at least 2 C1 rows")
    first, last = metrics[0], metrics[-1]
    minutes = (_parse(last["timestamp"]) - _parse(first["timestamp"])).total_seconds() / 60
    slope_rpm = (last["requests_per_min"] - first["requests_per_min"]) / minutes
    slope_cpu = (last["cpu_pct"] - first["cpu_pct"]) / minutes
    slope_mem = (last["mem_pct"] - first["mem_pct"]) / minutes

    now = _parse(last["timestamp"])
    series = []
    for step in range(1, int(horizon_minutes / step_minutes) + 1):
        ahead = step * step_minutes
        rpm = max(0.0, last["requests_per_min"] + slope_rpm * ahead)
        cpu = min(100.0, max(0.0, last["cpu_pct"] + slope_cpu * ahead))
        mem = min(100.0, max(0.0, last["mem_pct"] + slope_mem * ahead))
        series.append({
            "timestamp": (now + timedelta(minutes=ahead)).isoformat().replace("+00:00", "Z"),
            "requests_per_min": round(rpm),
            "cpu_pct": round(cpu, 1),
            "mem_pct": round(mem, 1),
            "lower": round(rpm * 0.92),
            "upper": round(rpm * 1.08),
        })

    exhaustion_at = None
    if slope_cpu > 0:
        mins = (cpu_threshold_pct - last["cpu_pct"]) / slope_cpu
        if 0 < mins <= horizon_minutes:
            exhaustion_at = (now + timedelta(minutes=mins)).isoformat().replace("+00:00", "Z")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": "naive-stub",
        "horizon_minutes": horizon_minutes,
        "step_minutes": step_minutes,
        "accuracy": {"mape_pct": 0.0, "rmse": 0.0},  # filled by real models
        "series": series,
        "cpu_threshold_pct": cpu_threshold_pct,
        "exhaustion_at": exhaustion_at,
    }


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.environ.get("C1_PATH", os.path.join(here, "contracts", "C1-metrics.sample.csv"))
    out = os.environ.get("C2_OUT", os.path.join(here, "data", "forecast.out.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(forecast(load_metrics(src)), f, indent=2)
    print(f"wrote {out}")
