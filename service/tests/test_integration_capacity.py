"""Cross-module checks that document other modules' bugs (not fixed here)."""
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


@pytest.mark.skip(reason="owned by Member 3")
def test_storage_growth_with_two_instances():
    # Each instance's disk grows 1 GB/day; baseline() divides by row count (2 per minute) and diffs
    # first/last rows across different instances (i-1 vs i-2), so it reports ~12.5 instead of ~1 GB/day.
    base = engine.run_baseline(rows_two_instances())
    assert base["storage_gb_per_day"] == pytest.approx(1.0, rel=0.1)
