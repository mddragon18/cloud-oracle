"""THE ONLY place that imports forecasting/ and capacity/ (HANDOFF §6).

If Modules 2/3 change signatures (e.g. DataFrame), only this file changes.
"""
import copy
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if (_REPO / "forecasting").is_dir() and str(_REPO) not in sys.path:  # in Lambda they're already top-level
    sys.path.insert(0, str(_REPO))

from capacity.plan import baseline as _baseline
from capacity.plan import plan as _plan
from forecasting.forecast import forecast as _forecast

from .schemas import validate

_SUM = ("requests_per_min", "net_in_kb", "net_out_kb")
_MEAN = ("avg_latency_ms", "p95_latency_ms", "cpu_pct", "mem_pct", "disk_used_gb")


def aggregate(rows: list[dict], mode: str = "per_minute_total") -> list[dict]:
    """C1 per-instance rows -> one row per minute (sum traffic, mean utilisation). Default mode "raw": Modules 2/3 aggregate themselves (Q1); per_minute_total is used by /metrics/recent."""
    if mode == "raw":
        return rows
    if mode != "per_minute_total":
        raise ValueError(f"unknown AGGREGATE_MODE {mode!r}")
    groups = defaultdict(list)
    for r in rows:
        groups[r["timestamp"]].append(r)
    out = []
    for ts in sorted(groups):
        g = groups[ts]
        row = {"timestamp": ts, "instance_id": "all", "instance_type": g[0]["instance_type"],
               "workload_pattern": g[0]["workload_pattern"], "instances": len(g)}
        row.update({k: sum(r[k] for r in g) for k in _SUM})
        row.update({k: sum(r[k] for r in g) / len(g) for k in _MEAN})
        out.append(row)
    return out


def run_forecast(rows: list[dict]) -> dict:
    """Aggregated C1 rows -> validated C2."""
    return validate("forecast", _forecast(rows))


def run_baseline(rows: list[dict]) -> dict:
    """Raw C1 rows -> Module 3 baseline dict."""
    return _baseline(rows)


def run_plan(c2: dict, base: dict) -> dict:
    """C2 + baseline -> validated C3. Never mutates c2."""
    return validate("plan", _plan(copy.deepcopy(c2), base))


def whatif(expected_rpm: int, rows: list[dict], mode: str = "raw") -> dict:
    """Fresh C3 with every forecast point set to expected_rpm. The tweaked C2 stays internal."""
    c2 = copy.deepcopy(run_forecast(aggregate(rows, mode)))
    for s in c2["series"]:
        s["requests_per_min"] = expected_rpm
    return run_plan(c2, run_baseline(rows))
