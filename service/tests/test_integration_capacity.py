"""Cross-module checks between service/ and capacity/."""
from datetime import UTC, datetime, timedelta

import pytest

from service.oracle_service import engine


def rows_two_instances(gb_per_day=1.0, minutes=60):
    t0 = datetime(2026, 10, 25, 10, tzinfo=UTC)
    out = []
    for m in range(minutes):
        for inst in ("i-1", "i-2"):
            out.append({"timestamp": (t0 + timedelta(minutes=m)).isoformat().replace("+00:00", "Z"),
                        "instance_id": inst, "instance_type": "t3.micro", "workload_pattern": "steady",
                        "requests_per_min": 500.0, "avg_latency_ms": 40.0, "p95_latency_ms": 80.0,
                        "cpu_pct": 30.0, "mem_pct": 50.0, "net_in_kb": 800.0, "net_out_kb": 6000.0,
                        "disk_used_gb": 3.0 + (1 if inst == "i-2" else 0) + gb_per_day * m / 1440})
    return out


def test_storage_growth_with_two_instances():
    # Growth is per instance: the offset between i-1 and i-2 must not read as growth.
    base = engine.run_baseline(rows_two_instances())
    assert base["storage_growth_gb_per_day"] == pytest.approx(1.0, rel=0.1)


def test_option_card_shows_memory_limit():
    from service.dashboard.app import option_card_html
    o = {"strategy": "scale_out", "instances": 3, "instance_type": "t3.micro", "usd_per_day": 0.81, "usd_per_hour": 0.034,
         "expected_latency_ms": 40.0, "single_point_of_failure": False}
    assert "limited by memory" not in option_card_html(o, True)
    assert "limited by memory" in option_card_html({**o, "memory_constrained": True}, True)
