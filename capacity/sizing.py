"""Capacity sizing calculations.

Calculates per-instance capacity and required instance counts based on
baseline workload estimates and a configurable target CPU utilisation.
"""
from __future__ import annotations

import math
from typing import Optional

from capacity import config


def calculate_capacity_per_instance(
    cpu_pct_per_100_rpm: float,
    target_cpu_pct: float = config.DEFAULT_CPU_TARGET_PCT,
) -> float:
    """Calculate requests per minute capacity per instance at target CPU.

    Formula:
        capacity_per_instance_rpm = target_cpu_pct * 100 / cpu_pct_per_100_rpm

    Args:
        cpu_pct_per_100_rpm: Observed CPU % per 100 requests/minute.
        target_cpu_pct: Target CPU utilisation percentage (0-100).

    Returns:
        Positive float: requests per minute a single instance can handle.

    Raises:
        ValueError: If inputs are invalid.
    """
    if not math.isfinite(cpu_pct_per_100_rpm) or cpu_pct_per_100_rpm <= 0:
        raise ValueError(
            f"cpu_pct_per_100_rpm must be positive and finite, got {cpu_pct_per_100_rpm}"
        )
    if not math.isfinite(target_cpu_pct) or target_cpu_pct <= 0 or target_cpu_pct >= 100:
        raise ValueError(
            f"target_cpu_pct must be strictly between 0 and 100, got {target_cpu_pct}"
        )
    capacity = target_cpu_pct * 100.0 / cpu_pct_per_100_rpm
    if not math.isfinite(capacity) or capacity <= 0:
        raise ValueError(f"Computed capacity is invalid: {capacity}")
    return float(capacity)


def calculate_instance_count(
    peak_requests_per_min: float,
    capacity_per_instance_rpm: float,
) -> int:
    """Calculate required instance count with safety margin.

    Formula:
        instances = ceil(peak_requests_per_min / capacity_per_instance_rpm) + 1

    Args:
        peak_requests_per_min: Forecast peak request rate.
        capacity_per_instance_rpm: Requests/min capacity per instance.

    Returns:
        Integer >= 1.

    Raises:
        ValueError: If inputs are invalid or result is not feasible.
    """
    if not math.isfinite(peak_requests_per_min) or peak_requests_per_min <= 0:
        raise ValueError(
            f"peak_requests_per_min must be positive and finite, got {peak_requests_per_min}"
        )
    if not math.isfinite(capacity_per_instance_rpm) or capacity_per_instance_rpm <= 0:
        raise ValueError(
            f"capacity_per_instance_rpm must be positive and finite, got {capacity_per_instance_rpm}"
        )
    raw = peak_requests_per_min / capacity_per_instance_rpm
    instances = math.ceil(raw) + config.SAFETY_MARGIN_INSTANCES
    if instances < 1:
        instances = 1
    return int(instances)
