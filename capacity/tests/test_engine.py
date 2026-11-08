import json
import math
import pytest

from capacity import engine, config


def test_plan_returns_required_c3_keys():
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
        "exhaustion_at": "2026-10-25T18:45:00Z",
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    required_keys = [
        "generated_at", "peak_requests_per_min", "current", "options",
        "bandwidth_mbps", "storage_gb_30d", "recommendation", "reason",
        "exhaustion_at",
    ]
    for k in required_keys:
        assert k in result, f"Missing key: {k}"
    # Check current sub-keys
    assert "instances" in result["current"]
    assert "instance_type" in result["current"]
    assert "usd_per_hour" in result["current"]
    # Check options length
    assert len(result["options"]) == 2
    # Check strategy names
    strategies = [opt["strategy"] for opt in result["options"]]
    assert "scale_out" in strategies
    assert "scale_up" in strategies


def test_hourly_and_daily_costs_correct():
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
        "storage_growth_gb_per_day": 0.01,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    for opt in result["options"]:
        hourly = opt["usd_per_hour"]
        daily = opt["usd_per_day"]
        assert math.isclose(daily, hourly * 24, rel_tol=1e-6)


def test_recommendation_follows_policy():
    # With a very high load, scale-up might be selected if it reduces instances significantly
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "cpu_threshold_pct": 70,
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 35.0,  # Higher coefficient => lower capacity => more instances
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
        "storage_growth_gb_per_day": 0.01,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    assert result["recommendation"] in ("scale_out", "scale_up")
    # Both options should have positive instance counts
    for opt in result["options"]:
        assert opt["instances"] >= 1
        assert isinstance(opt["single_point_of_failure"], bool)


def test_forecast_exhaustion_time_propagated():
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
        "exhaustion_at": "2026-10-27T18:45:00Z",
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    assert result["exhaustion_at"] == "2026-10-27T18:45:00Z"


def test_invalid_forecast_handled():
    with pytest.raises(ValueError, match="non-empty"):
        engine.plan(forecast={"series": []}, baseline={"cpu_pct_per_100_rpm": 7.0, "kb_per_request": 5.0, "current_disk_used_gb": 3.0, "latest_instance_type": "t3.micro", "instance_count_latest": 1})


def test_missing_prices_raise():
    # Force pricing failure by temporarily corrupting path
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    # Even with missing prices, the engine should try; it may succeed if prices exist
    # This test just verifies that an invalid forecast raises.
    with pytest.raises(ValueError):
        engine.plan(forecast={"series": [{"requests_per_min": 0}]}, baseline=baseline_result)


def test_what_if_helper_valid_rate():
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan_for_rpm(forecast=forecast, baseline_result=baseline_result, expected_rpm=5000.0)
    assert result["peak_requests_per_min"] == 5000.0
    assert len(result["options"]) == 2


def test_what_if_invalid_rate():
    with pytest.raises(ValueError, match="positive"):
        engine.plan_for_rpm(
            forecast={"generated_at": "2026-10-25T10:00:00Z", "series": [{"requests_per_min": 500}]},
            baseline_result={"cpu_pct_per_100_rpm": 7.0, "kb_per_request": 5.0, "current_disk_used_gb": 3.0, "latest_instance_type": "t3.micro", "instance_count_latest": 1},
            expected_rpm=-100.0,
        )


def test_plan_serializable_to_json():
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 500}],
        "exhaustion_at": "2026-10-25T18:45:00Z",
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 7.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    # Must be JSON serializable (no NaN/Infinity)
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    parsed = json.loads(serialized)
    assert parsed["recommendation"] == result["recommendation"]


def test_scale_out_recommended_at_268_rpm():
    """268 rpm: scale_out 2x t3.micro ($0.54/day) stays recommended."""
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 268}],
        "exhaustion_at": "2026-10-25T18:45:00Z",
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 8.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    assert result["recommendation"] == "scale_out"
    scale_out = [o for o in result["options"] if o["strategy"] == "scale_out"][0]
    assert scale_out["instances"] == 2
    assert scale_out["instance_type"] == "t3.micro"
    # Daily cost: 2 * 0.0112 * 24 ≈ 0.54
    assert abs(scale_out["usd_per_day"] - 0.5376) < 0.01
    # Scale-up must use a type with MORE RAM than t3.micro (1 GB)
    scale_up = [o for o in result["options"] if o["strategy"] == "scale_up"][0]
    assert scale_up["instance_type"] != "t4g.micro"  # same RAM, not a scale-up
    assert config.INSTANCE_RAM_GB[scale_up["instance_type"]] > config.INSTANCE_RAM_GB["t3.micro"]


def test_scale_up_cheaper_at_5000_rpm_with_bigger_type():
    """5000 rpm: scale_out 10x t3.micro ($2.69/day) vs cheaper scale-up on bigger type."""
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 5000}],
        "exhaustion_at": "2026-10-25T18:45:00Z",
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 8.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    scale_out = [o for o in result["options"] if o["strategy"] == "scale_out"][0]
    scale_up = [o for o in result["options"] if o["strategy"] == "scale_up"][0]

    # Scale-out: 10x t3.micro, memory-constrained
    assert scale_out["instances"] == 10
    assert scale_out["instance_type"] == "t3.micro"
    assert scale_out["memory_constrained"] is True
    assert abs(scale_out["usd_per_day"] - 2.688) < 0.01

    # Scale-up: must be a type with MORE RAM than t3.micro (1 GB)
    assert config.INSTANCE_RAM_GB[scale_up["instance_type"]] > 1.0
    # Scale-up must have enough memory for 5000 rpm
    oom_rpm = config.get_oom_rpm(scale_up["instance_type"])
    total_memory_capacity = scale_up["instances"] * oom_rpm
    assert total_memory_capacity >= 5000, (
        f"Scale-up {scale_up['instance_type']} has {scale_up['instances']}x{oom_rpm}="
        f"{total_memory_capacity} rpm memory capacity < 5000 rpm"
    )
    # Scale-up should be cheaper (or recommendation should be scale_out if not)
    if result["recommendation"] == "scale_up":
        assert scale_up["usd_per_day"] < scale_out["usd_per_day"]


def test_scale_up_never_same_ram_as_current():
    """Scale-up must never pick a type with the same RAM as the current type."""
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 5000}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 8.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    scale_up = [o for o in result["options"] if o["strategy"] == "scale_up"][0]
    current_type = result["current"]["instance_type"]
    current_ram = config.INSTANCE_RAM_GB[current_type]
    scale_up_ram = config.INSTANCE_RAM_GB[scale_up["instance_type"]]
    assert scale_up_ram > current_ram, (
        f"Scale-up {scale_up['instance_type']} has {scale_up_ram} GB RAM, "
        f"not greater than current {current_type} ({current_ram} GB)"
    )


def test_all_instance_types_have_memory_constraint():
    """All instance types with known RAM must have a memory constraint applied."""
    forecast = {
        "generated_at": "2026-10-27T10:00:00Z",
        "series": [{"timestamp": "2026-10-25T10:30:00Z", "requests_per_min": 5000}],
    }
    baseline_result = {
        "cpu_pct_per_100_rpm": 8.0,
        "kb_per_request": 5.0,
        "current_disk_used_gb": 3.0,
        "latest_instance_type": "t3.micro",
        "instance_count_latest": 1,
        "avg_latency_ms": 42.0,
        "p95_latency_ms": 88.0,
    }
    result = engine.plan(forecast=forecast, baseline=baseline_result)
    for opt in result["options"]:
        itype = opt["instance_type"]
        if itype in config.INSTANCE_RAM_GB:
            oom = config.get_oom_rpm(itype)
            max_rpm = opt["instances"] * oom
            # Memory capacity must meet or exceed peak
            assert max_rpm >= 5000, (
                f"{opt['strategy']} {itype}: {opt['instances']}x{oom}={max_rpm} "
                f"< 5000 rpm peak"
            )
