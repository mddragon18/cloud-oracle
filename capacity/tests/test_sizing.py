import math
import pytest
from capacity import sizing, config


def test_capacity_uses_target_cpu():
    # cpu_pct_per_100_rpm = 7 => capacity at 70% = 70*100/7 = 1000 rpm
    cap = sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=7.0, target_cpu_pct=70.0)
    assert math.isclose(cap, 1000.0, rel_tol=1e-3)


def test_capacity_at_60_and_80_produce_consistent_results():
    cap_60 = sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=7.0, target_cpu_pct=60.0)
    cap_80 = sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=7.0, target_cpu_pct=80.0)
    cap_70 = sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=7.0, target_cpu_pct=70.0)
    # Ordering: 60 < 70 < 80
    assert cap_60 < cap_70 < cap_80


def test_instance_count_formula():
    # With capacity 1000 and peak 500 => raw = 0.5 => ceil = 1 => +1 = 2
    count = sizing.calculate_instance_count(peak_requests_per_min=500.0, capacity_per_instance_rpm=1000.0)
    assert count == 2


def test_instance_count_integer_boundary():
    # Peak exactly at capacity => raw = 1 => ceil = 1 => +1 = 2
    count = sizing.calculate_instance_count(peak_requests_per_min=1000.0, capacity_per_instance_rpm=1000.0)
    assert count == 2


def test_non_integer_boundary():
    # Capacity 333 => peak 500 => raw 1.5 => ceil 2 => +1 = 3
    count = sizing.calculate_instance_count(peak_requests_per_min=500.0, capacity_per_instance_rpm=333.0)
    assert count == 3


def test_invalid_cpu_coefficient_rejected():
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=-1.0)
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=0.0)
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=float("nan"))


def test_invalid_target_cpu_rejected():
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=10.0, target_cpu_pct=0.0)
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=10.0, target_cpu_pct=100.0)
    with pytest.raises(ValueError):
        sizing.calculate_capacity_per_instance(cpu_pct_per_100_rpm=10.0, target_cpu_pct=-10.0)


def test_invalid_request_rate_rejected():
    with pytest.raises(ValueError):
        sizing.calculate_instance_count(peak_requests_per_min=0.0, capacity_per_instance_rpm=100.0)
    with pytest.raises(ValueError):
        sizing.calculate_instance_count(peak_requests_per_min=-100.0, capacity_per_instance_rpm=100.0)


def test_invalid_capacity_rejected():
    with pytest.raises(ValueError):
        sizing.calculate_instance_count(peak_requests_per_min=100.0, capacity_per_instance_rpm=0.0)
