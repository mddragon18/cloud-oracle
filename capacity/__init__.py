"""Capacity and Cost Engine (Member 3) for the Cloud Cost & Capacity Oracle.

Public interfaces:
    - baseline(metrics_df) -> dict
    - plan(forecast: dict, baseline: dict) -> dict
    - plan_for_rpm(forecast: dict, baseline_result: dict, expected_rpm: float) -> dict
"""
from capacity.baseline import baseline
from capacity.engine import plan, plan_for_rpm

__all__ = ["baseline", "plan", "plan_for_rpm"]
