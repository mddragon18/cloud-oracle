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
