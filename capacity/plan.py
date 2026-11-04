"""Backward-compatible wrapper around capacity.engine for repo imports.

The repo's service/api/app.py imports:
    from capacity.plan import baseline, plan as make_plan

This file preserves that interface by converting list-style C1 inputs
(passed by the forecasting stub) to pandas DataFrames before delegating
to capacity.engine.
"""
from __future__ import annotations

import math

from capacity.engine import plan as _engine_plan, plan_for_rpm as _engine_plan_for_rpm
from capacity.baseline import baseline as _baseline_df


def baseline(metrics):
    """Accept either a pandas DataFrame or a list of C1 row dicts.

    Returns the same dict shape as capacity.engine.plan() expects.
    """
    import pandas as pd
    if isinstance(metrics, pd.DataFrame):
        return _baseline_df(metrics)
    # List of dicts (from forecasting.load_metrics)
    df = pd.DataFrame(metrics)
    return _baseline_df(df)


def plan(forecast, base):
    """Delegate to capacity.engine.plan with backward-compatible names."""
    return _engine_plan(forecast, base)


def plan_for_rpm(forecast, base, expected_rpm):
    """Public what-if helper for Member 4 integration."""
    return _engine_plan_for_rpm(forecast, base, expected_rpm)
