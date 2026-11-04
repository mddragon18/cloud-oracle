"""Module 2: forecast(metrics) -> C2 dict (contracts/README.md).

ARIMA with daily Fourier terms on 15-minute load, once there are >= 2 days of
history (1 day to train + 1 held-out day for accuracy). Shorter inputs fall back
to a flat recent average that needs only the stdlib, so callers without
pandas/statsmodels (capacity, service tests on the 2-row sample) keep working.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

NUMERIC = ("requests_per_min", "avg_latency_ms", "p95_latency_ms", "cpu_pct",
           "mem_pct", "net_in_kb", "net_out_kb", "disk_used_gb")
MIN_HISTORY_MINUTES = 2 * 1440
NAIVE_WINDOW_MINUTES = 30  # short-history fallback averages the last 30 minutes
FOURIER_K = 3  # harmonics of the daily cycle; 3 fits a day/night shape without overfitting


def load_metrics(path):
    """C1 csv -> list of dicts (numbers converted)."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            row = {"timestamp": r["timestamp"], "instance_id": r["instance_id"],
                   "instance_type": r["instance_type"], "workload_pattern": r["workload_pattern"]}
            for k in NUMERIC:
                row[k] = float(r[k])
            rows.append(row)
    return rows


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _per_minute(rows):
    """All instances -> one point per minute: total rpm, mean cpu/mem. Sorted by time."""
    acc = {}
    for r in rows:
        a = acc.setdefault(r["timestamp"], [0.0, 0.0, 0.0, 0])
        a[0] += float(r["requests_per_min"])
        a[1] += float(r["cpu_pct"])
        a[2] += float(r["mem_pct"])
        a[3] += 1
    return sorted((_parse(ts), rpm, cpu / n, mem / n) for ts, (rpm, cpu, mem, n) in acc.items())


def forecast(metrics, horizon_minutes=1440, step_minutes=15, cpu_threshold_pct=70.0):
    """metrics: list of C1 row dicts or a C1 DataFrame -> C2 dict."""
    if hasattr(metrics, "to_dict"):
        metrics = metrics.to_dict("records")
    points = _per_minute(metrics)
    if len(points) < 2:
        raise ValueError("need at least 2 C1 timestamps")
    span = (points[-1][0] - points[0][0]).total_seconds() / 60
    if span >= MIN_HISTORY_MINUTES:
        series, accuracy, model = _arima(points, horizon_minutes, step_minutes)
    else:
        series, accuracy, model = _naive(points, horizon_minutes, step_minutes)

    exhaustion_at = next((s["timestamp"] for s in series if s["cpu_pct"] >= cpu_threshold_pct), None)
    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "model": model,
        "horizon_minutes": horizon_minutes,
        "step_minutes": step_minutes,
        "accuracy": accuracy,
        "series": series,
        "cpu_threshold_pct": cpu_threshold_pct,
        "exhaustion_at": exhaustion_at,
    }


def _row(ts, rpm, cpu, mem, lower, upper):
    return {"timestamp": _iso(ts), "requests_per_min": round(max(0.0, rpm)),
            "cpu_pct": round(min(100.0, max(0.0, cpu)), 1),
            "mem_pct": round(min(100.0, max(0.0, mem)), 1),
            "lower": round(max(0.0, lower)), "upper": round(max(0.0, upper))}


def _naive(points, horizon_minutes, step_minutes):
    """Flat line at the recent average, banded by recent spread. Accuracy is null: nothing held out.

    Deliberately no trend: extrapolating minutes of noisy data over 24 h ran away
    (20 real rows -> 84,728 rpm forecast, service/PROGRESS.md).
    """
    import statistics
    recent = points[-NAIVE_WINDOW_MINUTES:]
    rpm = statistics.fmean(p[1] for p in recent)
    cpu = statistics.fmean(p[2] for p in recent)
    mem = statistics.fmean(p[3] for p in recent)
    spread = statistics.pstdev(p[1] for p in recent)
    band = max(1.28 * spread, 0.08 * rpm)  # 80% band like ARIMA's, at least +-8%
    last = points[-1][0]
    series = [_row(last + timedelta(minutes=step * step_minutes), rpm, cpu, mem, rpm - band, rpm + band)
              for step in range(1, horizon_minutes // step_minutes + 1)]
    return series, {"mape_pct": None, "rmse": None}, "naive"


# ---- ARIMA path (pandas/statsmodels imported lazily) ----

def _frame(points, step_minutes):
    import pandas as pd
    df = pd.DataFrame(points, columns=["t", "rpm", "cpu", "mem"]).set_index("t")
    return df.resample(f"{step_minutes}min").mean().interpolate(limit_direction="both")


def _fourier(start, n, period):
    import numpy as np
    t = np.arange(start, start + n)
    cols = []
    for k in range(1, FOURIER_K + 1):
        cols += [np.sin(2 * np.pi * k * t / period), np.cos(2 * np.pi * k * t / period)]
    return np.column_stack(cols)


def _fit_predict(y, steps, period):
    """Fit ARIMA(2,0,1)+trend+daily Fourier on y; return (mean, lower, upper) arrays for `steps` ahead."""
    import warnings
    import numpy as np
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence chatter on flat series
        fit = ARIMA(y, exog=_fourier(0, len(y), period), order=(2, 0, 1), trend="ct").fit()
        fc = fit.get_forecast(steps, exog=_fourier(len(y), steps, period))
    ci = np.asarray(fc.conf_int(alpha=0.2))  # 80% band
    return np.asarray(fc.predicted_mean), ci[:, 0], ci[:, 1]


def errors(actual, predicted):
    """MAE / RMSE / MAPE (%, over non-zero actuals)."""
    import numpy as np
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    nz = a != 0
    return {"mae": float(np.mean(np.abs(a - p))),
            "rmse": float(np.sqrt(np.mean((a - p) ** 2))),
            "mape_pct": float(np.mean(np.abs((a[nz] - p[nz]) / a[nz])) * 100) if nz.any() else None}


def holdout(points, step_minutes=15):
    """Train on all but the last day, predict that day. Returns (actual Series, predicted array, errors)."""
    df = _frame(points, step_minutes)
    period = 1440 // step_minutes
    pred, _, _ = _fit_predict(df["rpm"].to_numpy()[:-period], period, period)
    actual = df["rpm"].iloc[-period:]
    return actual, pred, errors(actual.to_numpy(), pred)


def _arima(points, horizon_minutes, step_minutes):
    import numpy as np
    _, _, err = holdout(points, step_minutes)
    df = _frame(points, step_minutes)
    period = 1440 // step_minutes
    mean, lower, upper = _fit_predict(df["rpm"].to_numpy(), horizon_minutes // step_minutes, period)
    # CPU/mem follow load: least-squares line learned from history
    cpu_a, cpu_b = np.polyfit(df["rpm"], df["cpu"], 1)
    mem_a, mem_b = np.polyfit(df["rpm"], df["mem"], 1)
    last = df.index[-1].to_pydatetime()
    series = [_row(last + timedelta(minutes=(i + 1) * step_minutes), m,
                   cpu_a * m + cpu_b, mem_a * m + mem_b, lo, hi)
              for i, (m, lo, hi) in enumerate(zip(mean, lower, upper))]
    accuracy = {"mape_pct": None if err["mape_pct"] is None else round(err["mape_pct"], 2),
                "rmse": round(err["rmse"], 2)}
    return series, accuracy, "arima"


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.environ.get("C1_PATH", os.path.join(here, "contracts", "C1-metrics.sample.csv"))
    out = os.environ.get("C2_OUT", os.path.join(here, "data", "forecast.out.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(forecast(load_metrics(src)), f, indent=2)
    print(f"wrote {out}")
