"""Synthetic C1 metrics in the 4 Locust patterns (steady/cycle/spike/growth).

Used by tests and by the team until real metrics arrive. Also turns any
requests-per-minute series into C1 rows (`c1_from_rpm`), which the loaders reuse.
"""
import numpy as np
import pandas as pd

C1_COLUMNS = ["timestamp", "instance_id", "instance_type", "requests_per_min", "avg_latency_ms",
              "p95_latency_ms", "cpu_pct", "mem_pct", "net_in_kb", "net_out_kb", "disk_used_gb",
              "workload_pattern"]
PATTERNS = ("steady", "cycle", "spike", "growth")

# shortcut: CPU/latency/network per request are assumed (500 rpm -> ~35% CPU, like the C1 sample);
# replace with Member 1's measured t3.micro numbers once the AWS run lands.
CPU_BASE, CPU_PER_RPM = 5.0, 0.06


def rpm_pattern(pattern, days=7, start="2026-10-01T00:00:00Z", seed=0):
    """Per-minute requests_per_min series (pd.Series indexed by UTC minute)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 1440, freq="min")
    t_days = np.arange(len(idx)) / 1440
    if pattern == "steady":
        rpm = np.full(len(idx), 500.0)
    elif pattern == "cycle":
        rpm = 500 + 300 * np.sin(2 * np.pi * (t_days - 0.25))  # trough ~00:00, peak ~12:00
    elif pattern == "spike":
        rpm = np.full(len(idx), 500.0)
        for d in range(days):  # one 30-min 10x spike per day at a random time
            s = d * 1440 + int(rng.integers(0, 1440 - 30))
            rpm[s:s + 30] *= 10
    elif pattern == "growth":
        rpm = 300 + 100 * t_days  # +100 rpm per day
    else:
        raise ValueError(f"unknown pattern {pattern!r}; expected one of {PATTERNS}")
    rpm = rpm * rng.normal(1.0, 0.05, len(idx))
    return pd.Series(np.clip(rpm, 0, None), index=idx, name="requests_per_min")


def c1_from_rpm(rpm, pattern, cpu=None, instance_id="i-01", instance_type="t3.micro", seed=0):
    """Per-minute rpm series (+ optional real cpu series) -> C1 DataFrame."""
    rng = np.random.default_rng(seed)
    n = len(rpm)
    r = rpm.to_numpy(dtype=float)
    if cpu is None:
        cpu_v = CPU_BASE + CPU_PER_RPM * r + rng.normal(0, 1.0, n)
    else:
        cpu_v = cpu.to_numpy(dtype=float)
    avg_lat = 30 + 0.02 * r + rng.normal(0, 1.0, n)
    days = np.arange(n) / 1440
    return pd.DataFrame({
        "timestamp": rpm.index.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instance_id": instance_id,
        "instance_type": instance_type,
        "requests_per_min": np.round(r).astype(int),
        "avg_latency_ms": np.round(avg_lat, 1),
        "p95_latency_ms": np.round(avg_lat * 2.1, 1),
        "cpu_pct": np.round(np.clip(cpu_v, 0, 100), 1),
        "mem_pct": np.round(np.clip(50 + 0.005 * r + rng.normal(0, 0.5, n), 0, 100), 1),
        "net_in_kb": np.round(1.6 * r).astype(int),
        "net_out_kb": np.round(12.5 * r).astype(int),
        "disk_used_gb": np.round(3.0 + 0.01 * days, 2),
        "workload_pattern": pattern,
    }, columns=C1_COLUMNS)


def generate(pattern, days=7, start="2026-10-01T00:00:00Z", seed=0):
    """C1 DataFrame for one of the 4 patterns."""
    return c1_from_rpm(rpm_pattern(pattern, days, start, seed), pattern, seed=seed)


if __name__ == "__main__":
    import argparse
    import os
    p = argparse.ArgumentParser(description="write synthetic C1 csv")
    p.add_argument("pattern", choices=PATTERNS)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                                f"synthetic-{a.pattern}.csv")
    generate(a.pattern, a.days).to_csv(out, index=False)
    print(f"wrote {out}")
