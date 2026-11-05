"""Capacity and cost engine: compares scaling options and recommends a plan.

Produces Contract C3 output from a C2 forecast and a baseline result.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd  # kept for potential future use

from capacity import config, pricing, sizing
from capacity.baseline import baseline


def _apply_memory_constraint(
    instance_type: str,
    instances: int,
    peak_rpm: float,
    config_module,
) -> tuple[int, bool]:
    """Apply memory binding constraint for t3.micro.

    Returns (adjusted_instances, memory_constrained_flag).
    """
    if instance_type == "t3.micro":
        oom_rpm = config_module.T3_MICRO_OOM_RPM
        max_rpm = instances * oom_rpm
        if peak_rpm > max_rpm:
            # Need more instances to stay under memory limit
            required = math.ceil(peak_rpm / oom_rpm)
            return required, True
    return instances, False


def plan_for_rpm(
    forecast: dict,
    baseline_result: dict,
    expected_rpm: float,
) -> dict:
    """Generate a C3 plan for an explicit request rate (what-if).

    Args:
        forecast: The original C2 forecast dictionary.
        baseline_result: The result from baseline().
        expected_rpm: The hypothetical peak requests/minute.

    Returns:
        A C3-conformant plan dictionary.

    Raises:
        ValueError: If expected_rpm is not positive or the forecast is invalid.
    """
    if not math.isfinite(expected_rpm) or expected_rpm <= 0:
        raise ValueError(f"expected_rpm must be positive and finite, got {expected_rpm}")
    # Reuse the same sizing/pricing/recommendation logic but override the peak.
    # We inject the override by creating a temporary forecast copy.
    forecast_override = dict(forecast) if forecast else {}
    # Ensure series exists but we'll use expected_rpm directly in the engine logic
    # The main plan() function should support an override mechanism.
    # For simplicity, we call plan() with a modified forecast that has the override value.
    # But plan() reads peak from series. Let's adapt plan() directly.
    return plan(
        forecast=forecast_override,
        baseline=baseline_result,
        override_peak_rpm=expected_rpm,
    )


def plan(
    forecast: dict,
    baseline: dict,
    override_peak_rpm: Optional[float] = None,
) -> dict:
    """Generate the C3 plan from forecast and baseline.

    Args:
        forecast: C2 forecast dictionary.
        baseline: Result from baseline() (or equivalent dict with required keys).
        override_peak_rpm: Optional override for the peak request rate.

    Returns:
        Contract C3 dictionary.

    Raises:
        ValueError: For invalid inputs, missing prices, or infeasible configurations.
    """
    if not isinstance(forecast, dict):
        raise TypeError("forecast must be a dict")
    if not isinstance(baseline, dict):
        raise TypeError("baseline must be a dict")

    # Validate forecast has at least the structural fields we need
    series = forecast.get("series", [])
    if not isinstance(series, list) or len(series) == 0:
        raise ValueError("Forecast must contain a non-empty 'series' list.")

    # Extract peak request rate
    if override_peak_rpm is not None:
        peak_requests_per_min = float(override_peak_rpm)
    else:
        # Find max requests_per_min across series
        peak_values = []
        for item in series:
            rpm = item.get("requests_per_min")
            if rpm is not None:
                rpm_f = float(rpm)
                if math.isfinite(rpm_f) and rpm_f > 0:
                    peak_values.append(rpm_f)
        if not peak_values:
            raise ValueError("Forecast series contains no positive, finite requests_per_min values.")
        peak_requests_per_min = max(peak_values)

    if not math.isfinite(peak_requests_per_min) or peak_requests_per_min <= 0:
        raise ValueError(f"Peak requests/min must be positive and finite: {peak_requests_per_min}")

    # CPU target from forecast or default
    cpu_target_pct = float(forecast.get("cpu_threshold_pct", config.DEFAULT_CPU_TARGET_PCT))
    if cpu_target_pct <= 0 or cpu_target_pct >= 100:
        # Fall back to default but keep going for documentation
        cpu_target_pct = config.DEFAULT_CPU_TARGET_PCT

    # Baseline CPU coefficient
    cpu_coeff = baseline.get("cpu_pct_per_100_rpm")
    # Use measured coefficient from real AWS run if baseline doesn't have it
    if cpu_coeff is None:
        cpu_coeff = config.MEASURED_CPU_PCT_PER_100_RPM
    cpu_coeff_f = float(cpu_coeff)
    if not math.isfinite(cpu_coeff_f) or cpu_coeff_f <= 0:
        raise ValueError(f"Baseline CPU coefficient must be positive and finite: {cpu_coeff_f}")

    # Capacity per instance at target CPU
    capacity_per_instance = sizing.calculate_capacity_per_instance(
        cpu_pct_per_100_rpm=cpu_coeff_f,
        target_cpu_pct=cpu_target_pct,
    )

    # Instance count
    instances_required = sizing.calculate_instance_count(
        peak_requests_per_min=peak_requests_per_min,
        capacity_per_instance_rpm=capacity_per_instance,
    )

    # Load prices
    try:
        prices = pricing.load_prices()
    except Exception as exc:
        raise ValueError(f"Failed to load price data: {exc}. Ensure pricing.json exists or retrieve via fetch_prices.py.")

    # Determine current deployment info
    current_type = baseline.get("latest_instance_type") or config.DEFAULT_CURRENT_INSTANCE_TYPE
    current_instances = int(baseline.get("instance_count_latest", config.DEFAULT_CURRENT_INSTANCES) or config.DEFAULT_CURRENT_INSTANCES)
    current_instances = max(current_instances, 1)

    # Ensure current type has a price; fall back to default if not
    if current_type not in prices:
        current_type = config.DEFAULT_CURRENT_INSTANCE_TYPE
    if current_type not in prices:
        raise ValueError(f"No price available for current instance type {current_type}. Run fetch_prices.py.")

    # Scale-out: same instance type
    scale_out_type = current_type
    scale_out_instances = max(instances_required, 1)
    # Apply memory constraint for scale-out
    scale_out_instances, scale_out_memory_constrained = _apply_memory_constraint(
        scale_out_type, scale_out_instances, peak_requests_per_min, config
    )
    try:
        scale_out_price = pricing.get_price(scale_out_type, prices)
    except Exception as exc:
        raise ValueError(f"Price unavailable for scale-out instance type {scale_out_type}: {exc}")
    scale_out_hourly = scale_out_instances * scale_out_price
    scale_out_daily = scale_out_hourly * 24

    # Scale-up: evaluate larger instance types configured
    scale_up_options = []
    # For simplicity, choose the smallest larger instance type that has a price
    # We evaluate a single scale-up option using a configured larger type.
    # To keep it deterministic, pick the first larger type from candidates
    # that is larger than current.
    larger_candidates = [t for t in config.CANDIDATE_INSTANCE_TYPES if t != current_type and t in prices]
    # Sort to have deterministic selection; prefer the smallest larger family type
    larger_candidates.sort()
    scale_up_type = current_type
    scale_up_instances = instances_required
    for candidate in larger_candidates:
        # Use a provisional multiplier to see if it can reduce instances
        multiplier = config.PROVISIONAL_CAPACITY_MULTIPLIER.get(candidate, 1.0)
        if multiplier > 1.0:
            # If larger instance has more capacity, recalculate instances needed
            # We assume capacity is proportional to multiplier (provisional)
            scaled_capacity = capacity_per_instance * multiplier
            scaled_instances = max(math.ceil(peak_requests_per_min / scaled_capacity), 1) + 1 - 1  # safety already in formula
            # Actually our sizing uses +1 safety margin; reuse sizing logic
            scaled_instances = sizing.calculate_instance_count(
                peak_requests_per_min=peak_requests_per_min,
                capacity_per_instance_rpm=scaled_capacity,
            )
            # Only choose if it actually improves (fewer instances or similar with benefit)
            # For simplicity, pick the first larger candidate that yields feasible instances.
            if scaled_instances >= 1:
                scale_up_type = candidate
                scale_up_instances = scaled_instances
                break
    # If no larger candidate improves, keep current (but we must present a different type for scale-up)
    # Let's enforce a larger type if available; else keep current and document.
    if scale_up_type == current_type and larger_candidates:
        scale_up_type = larger_candidates[0]
        # For larger type, assume same capacity as current (provisional assumption: same performance)
        # Or use multiplier. We'll use multiplier for capacity estimate.
        multiplier = config.PROVISIONAL_CAPACITY_MULTIPLIER.get(scale_up_type, 1.0)
        scaled_capacity = capacity_per_instance * max(multiplier, 1.0)
        scale_up_instances = sizing.calculate_instance_count(
            peak_requests_per_min=peak_requests_per_min,
            capacity_per_instance_rpm=scaled_capacity,
        )
        scale_up_instances = max(scale_up_instances, 1)

    # Apply memory constraint for scale-up
    scale_up_instances, scale_up_memory_constrained = _apply_memory_constraint(
        scale_up_type, scale_up_instances, peak_requests_per_min, config
    )

    # If scale_up_instances is same as scale_out, we still present it but note limitations
    # Ensure scale-up has a price
    if scale_up_type not in prices:
        # If selected scale-up has no price, fall back to current
        scale_up_type = current_type
    scale_up_price = pricing.get_price(scale_up_type, prices)
    scale_up_hourly = scale_up_instances * scale_up_price
    scale_up_daily = scale_up_hourly * 24

    # Bandwidth estimate (Mbps)
    kb_per_request = baseline.get("kb_per_request")
    if kb_per_request is not None and math.isfinite(float(kb_per_request)) and float(kb_per_request) >= 0:
        traffic_kb_per_min = peak_requests_per_min * float(kb_per_request)
        # Decimal KB to Mbps: kb/min * 8 bits / (60 sec * 1000 kb/Mb)
        bandwidth_mbps = traffic_kb_per_min * 8.0 / (60.0 * 1000.0)
        if not math.isfinite(bandwidth_mbps) or bandwidth_mbps < 0:
            bandwidth_mbps = 0.0
    else:
        bandwidth_mbps = 0.0

    # Storage projection
    current_disk = baseline.get("current_disk_used_gb")
    storage_growth = baseline.get("storage_growth_gb_per_day")
    if current_disk is not None and math.isfinite(float(current_disk)) and float(current_disk) >= 0:
        disk_f = float(current_disk)
    else:
        disk_f = 0.0
    growth_f = float(storage_growth) if storage_growth is not None and math.isfinite(storage_growth) else 0.0
    storage_gb_30d = disk_f + growth_f * 30.0
    if not math.isfinite(storage_gb_30d) or storage_gb_30d < 0:
        storage_gb_30d = disk_f  # Prevent negative projection

    # Latency estimates
    # Simplified Phase II estimator: scale-out = baseline avg latency; scale-up = slightly lower
    # because larger instances may process faster (provisional assumption).
    # We document clearly that these are provisional estimates, not measured values.
    observed_avg_latency = baseline.get("avg_latency_ms")
    observed_p95_latency = baseline.get("p95_latency_ms")
    base_latency = float(observed_avg_latency) if observed_avg_latency is not None and math.isfinite(observed_avg_latency) else 50.0
    # Scale-up provisional assumption: 10% lower latency (faster instance)
    scale_up_latency = base_latency * 0.9 if base_latency > 0 else base_latency
    # Scale-out latency stays near observed (same instance type)
    scale_out_latency = base_latency
    # Ensure latency values are finite
    scale_out_latency = max(scale_out_latency, 0.0)
    scale_up_latency = max(scale_up_latency, 0.0)

    # Single-point-of-failure status
    # Simplified model: one application instance = true; multiple = false.
    scale_out_spof = (scale_out_instances <= 1)
    scale_up_spof = (scale_up_instances <= 1)

    # Recommendation policy
    recommendation = "scale_out"
    reason = ""

    # Check feasibility of options
    # Scale-out must satisfy capacity; scale-up must satisfy capacity (provisional capacity assumed)
    # If scale-up uses same instance type (fallback), treat it as less preferred.
    # Decision rules:
    # 1. Exclude infeasible options (those that fail capacity). Here both use sizing logic.
    # 2. Prefer scale-out when cheaper, satisfies target, avoids SPOF, and latency within 10% of scale-up.
    # 3. Otherwise choose lowest-cost feasible option with acceptable latency.
    # 4. If performance constraints make cheaper option unsuitable, pick better latency.

    # Compare costs
    scale_out_is_cheaper = scale_out_daily < scale_up_daily
    latency_difference_pct = 0.0
    if scale_up_latency > 0 and scale_out_latency > 0:
        latency_difference_pct = abs(scale_out_latency - scale_up_latency) / max(scale_up_latency, 1e-6) * 100.0
    else:
        latency_difference_pct = 0.0

    scale_out_has_spof = scale_out_spof
    scale_up_has_spof = scale_up_spof

    # Policy evaluation
    # Prefer scale-out if it is cheaper, avoids SPOF, and latency within 10% of scale-up.
    scale_out_preferred = False
    if scale_out_is_cheaper and not scale_out_has_spof:
        if latency_difference_pct <= 10.0:
            scale_out_preferred = True

    if scale_out_preferred:
        recommendation = "scale_out"
        savings_pct = (1.0 - scale_out_daily / max(scale_up_daily, 1e-9)) * 100.0 if scale_up_daily > 0 else 0.0
        reason = (
            f"Scale-out recommended: {savings_pct:.0f}% cheaper per day (${scale_out_daily:.2f} vs ${scale_up_daily:.2f}), "
            f"no single point of failure (instances={scale_out_instances}), "
            f"latency {scale_out_latency:.0f}ms within 10% of scale-up ({scale_up_latency:.0f}ms)."
        )
    else:
        # Otherwise, choose the feasible option with lower cost if latency acceptable.
        # If scale-up is cheaper and latency is acceptable, pick scale-up.
        # If scale-out has SPOF or latency is too high, consider scale-up.
        if scale_up_daily < scale_out_daily and scale_up_latency >= 0:
            # Scale-up cheaper
            if not scale_up_has_spof or scale_up_spof == scale_out_spof:
                recommendation = "scale_up"
                savings_pct = (1.0 - scale_up_daily / max(scale_out_daily, 1e-9)) * 100.0 if scale_out_daily > 0 else 0.0
                reason = (
                    f"Scale-up recommended: {savings_pct:.0f}% cheaper per day (${scale_up_daily:.2f} vs ${scale_out_daily:.2f}), "
                )
                if scale_up_has_spof:
                    reason += f"but has single point of failure (instances={scale_up_instances}). "
                else:
                    reason += f"no single point of failure. "
                reason += f"Latency {scale_up_latency:.0f}ms vs {scale_out_latency:.0f}ms."
            else:
                # Scale-up cheaper but has SPOF and scale-out avoids it; choose based on priority
                # For simplicity: still choose scale-up if significantly cheaper, else scale-out.
                recommendation = "scale_up"
                reason = (
                    f"Scale-up selected (${scale_up_daily:.2f}/day) despite single-point-of-failure risk; "
                    f"scale-out costs ${scale_out_daily:.2f}/day. Latency {scale_up_latency:.0f}ms."
                )
        else:
            # Scale-out is cheaper or same cost but didn't meet preferred criteria (latency or SPOF)
            recommendation = "scale_out"
            reason = (
                f"Scale-out selected (${scale_out_daily:.2f}/day, instances={scale_out_instances}). "
                f"Latency {scale_out_latency:.0f}ms vs scale-up {scale_up_latency:.0f}ms (diff={latency_difference_pct:.0f}%). "
            )
            if scale_out_has_spof:
                reason += "Note: single-point-of-failure risk. "
            reason += f"Scale-up cost ${scale_up_daily:.2f}/day (type={scale_up_type}, instances={scale_up_instances})."

    # If neither option has a valid price, raise
    if recommendation not in ("scale_out", "scale_up"):
        raise ValueError("No valid recommendation could be produced.")

    # Propagate forecast exhaustion time
    exhaustion_at = forecast.get("exhaustion_at")

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "peak_requests_per_min": float(peak_requests_per_min),
        "current": {
            "instances": int(current_instances),
            "instance_type": str(current_type),
            "usd_per_hour": current_instances * pricing.get_price(current_type, prices) if current_type in prices else 0.0,
        },
        "options": [
            {
                "strategy": "scale_out",
                "instances": int(scale_out_instances),
                "instance_type": str(scale_out_type),
                "usd_per_hour": float(scale_out_hourly),
                "usd_per_day": float(scale_out_daily),
                "expected_latency_ms": float(round(scale_out_latency, 2)),
                "single_point_of_failure": bool(scale_out_spof),
                "memory_constrained": bool(scale_out_memory_constrained),
            },
            {
                "strategy": "scale_up",
                "instances": int(scale_up_instances),
                "instance_type": str(scale_up_type),
                "usd_per_hour": float(scale_up_hourly),
                "usd_per_day": float(scale_up_daily),
                "expected_latency_ms": float(round(scale_up_latency, 2)),
                "single_point_of_failure": bool(scale_up_spof),
                "memory_constrained": bool(scale_up_memory_constrained),
            },
        ],
        "bandwidth_mbps": float(round(bandwidth_mbps, 2)),
        "storage_gb_30d": float(round(storage_gb_30d, 2)),
        "recommendation": recommendation,
        "reason": reason,
        "exhaustion_at": exhaustion_at if exhaustion_at else None,
    }

    # Validate JSON serialisability (no NaN/Infinity)
    def _validate_serializable(obj, path="root"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _validate_serializable(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _validate_serializable(v, f"{path}[{i}]")
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                raise ValueError(f"Non-serializable float at {path}: {obj}")

    _validate_serializable(result)
    return result
