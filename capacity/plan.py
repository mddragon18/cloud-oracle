"""Module 3 stub: baseline(metrics) and plan(forecast, baseline) -> C3 dict.

Stub formulas per the plan: instances = ceil(peak ÷ capacity at 70% CPU) + 1.
Prices here are PLACEHOLDERS — replace with pricing.json from the Price List API
(Member 3, Phase II). Latency model is a stub; M/M/c lands in Phase III.
"""
import math

PLACEHOLDER_PRICE = {
    "t3.micro": 0.0112,
    "t3.small": 0.0160,
    "t3.medium": 0.0320,
    "t3.large": 0.0800,
    "t3.xlarge": 0.1790,
}
CURRENT = {"instances": 1, "instance_type": "t3.micro"}


def baseline(metrics):
    """C1 rows -> dict: cpu % per 100 req/min, KB per request, storage growth/day."""
    rpm = sum(r["requests_per_min"] for r in metrics) / len(metrics)
    cpu = sum(r["cpu_pct"] for r in metrics) / len(metrics)
    cpu_per_100 = cpu / rpm * 100 if rpm > 0 else float("inf")
    kb_per_req = sum(r["net_in_kb"] for r in metrics) / sum(r["requests_per_min"] for r in metrics) if rpm > 0 else 0.0
    minutes = len(metrics)
    storage_per_day = (metrics[-1]["disk_used_gb"] - metrics[0]["disk_used_gb"]) / minutes * 1440
    capacity_rpm_at_70 = 70 / cpu_per_100 * 100 if cpu_per_100 > 0 else 0.0
    return {
        "cpu_pct_per_100rpm": round(cpu_per_100, 3),
        "kb_per_req": round(kb_per_req, 3),
        "storage_gb_per_day": round(max(storage_per_day, 0.05), 3),
        "capacity_rpm_at_70": round(capacity_rpm_at_70),
    }


def plan(forecast, base):
    """C2 dict + baseline(metrics) dict -> C3 dict."""
    peak = max(s["requests_per_min"] for s in forecast["series"])
    cap = base["capacity_rpm_at_70"]
    instances = math.ceil(peak / cap) + 1 if cap > 0 else 1

    out_usd_h = instances * PLACEHOLDER_PRICE["t3.micro"]
    up_usd_h = PLACEHOLDER_PRICE["t3.xlarge"]
    options = [
        {"strategy": "scale_out", "instances": instances, "instance_type": "t3.micro",
         "usd_per_hour": round(out_usd_h, 3), "usd_per_day": round(out_usd_h * 24, 2),
         "expected_latency_ms": 52, "single_point_of_failure": False},
        {"strategy": "scale_up", "instances": 1, "instance_type": "t3.xlarge",
         "usd_per_hour": round(up_usd_h, 3), "usd_per_day": round(up_usd_h * 24, 2),
         "expected_latency_ms": 47, "single_point_of_failure": True},
    ]
    rec = options[0] if options[0]["usd_per_day"] <= options[1]["usd_per_day"] else options[1]
    reason = (
        f"{round(100 * (1 - out_usd_h / up_usd_h))}% cheaper per day and no "
        "single point of failure; latency within 10% of scale-up"
        if rec["strategy"] == "scale_out" else "scale-up cheaper; keep SPOF risk in mind"
    )
    bandwidth_mbps = peak * base["kb_per_req"] * 8 / 60 / 1024
    storage_gb_30d = forecast_last_disk_gb(forecast) + base["storage_gb_per_day"] * 30
    return {
        "generated_at": forecast["generated_at"],
        "peak_requests_per_min": peak,
        "current": {**CURRENT, "usd_per_hour": PLACEHOLDER_PRICE[CURRENT["instance_type"]]},
        "options": options,
        "bandwidth_mbps": round(bandwidth_mbps, 1),
        "storage_gb_30d": round(storage_gb_30d, 1),
        "recommendation": rec["strategy"],
        "reason": reason,
        "exhaustion_at": forecast["exhaustion_at"],
    }


def forecast_last_disk_gb(forecast):
    """Placeholder storage anchor; Member 3 replaces from C1 history."""
    return 3.1


if __name__ == "__main__":
    import json
    import os
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    from forecasting.forecast import forecast as make_forecast, load_metrics

    metrics = load_metrics(os.path.join(here, "contracts", "C1-metrics.sample.csv"))
    fc = make_forecast(metrics)
    result = plan(fc, baseline(metrics))
    out = os.path.join(here, "data", "plan.out.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {out}")
