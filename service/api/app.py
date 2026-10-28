"""Module 4 stub: the 5 API endpoints, first serving sample files.

Phase II: serve contracts samples. Then switch to calling Modules 2 and 3 and
storing in DynamoDB (Phase III). Functions are plain dict-returning so the
Streamlit dashboard and tests can call them without HTTP.
"""
import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from capacity.plan import baseline, plan as make_plan          # noqa: E402
from forecasting.forecast import forecast as make_forecast, load_metrics  # noqa: E402

SAMPLE_DIR = os.environ.get("SAMPLE_DIR", os.path.join(REPO, "contracts"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(REPO, "data"))


def _read(path):
    with open(path) as f:
        return json.load(f)


def latest_forecast():
    real = os.path.join(DATA_DIR, "forecast.out.json")
    return _read(real if os.path.exists(real) else os.path.join(SAMPLE_DIR, "C2-forecast.sample.json"))


def latest_plan():
    real = os.path.join(DATA_DIR, "plan.out.json")
    return _read(real if os.path.exists(real) else os.path.join(SAMPLE_DIR, "C3-plan.sample.json"))


def whatif_plan(expected_rpm):
    """POST /plan: fresh C3 for a what-if load, calling Module 3 directly."""
    metrics = load_metrics(os.path.join(SAMPLE_DIR, "C1-metrics.sample.csv"))
    fc = make_forecast(metrics)
    fc["peak_override"] = True
    for s in fc["series"]:
        s["requests_per_min"] = expected_rpm
    return make_plan(fc, baseline(metrics))


def history(days=7):
    out_dir = os.path.join(DATA_DIR, "plans")
    if not os.path.isdir(out_dir):
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    plans = []
    for name in sorted(os.listdir(out_dir)):
        if name.endswith(".json"):
            plans.append(_read(os.path.join(out_dir, name)))
    return plans


def health():
    return {"status": "ok"}


try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="oracle-service")

    class WhatIf(BaseModel):
        expected_rpm: int

    @app.get("/forecast/latest")
    def api_forecast():
        return latest_forecast()

    @app.get("/plan/latest")
    def api_plan():
        return latest_plan()

    @app.post("/plan")
    def api_post_plan(body: WhatIf):
        return whatif_plan(body.expected_rpm)

    @app.get("/history")
    def api_history(days: int = 7):
        return {"plans": history(days)}

    @app.get("/health")
    def api_health():
        return health()
except ImportError:  # API needs fastapi; function stubs work without it
    app = None
