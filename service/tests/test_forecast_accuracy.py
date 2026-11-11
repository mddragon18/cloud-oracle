from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from service.oracle_service import api, core
from service.oracle_service.config import REPO
from service.oracle_service.store import LocalStore, iso

HDR = (REPO / "contracts/C1-metrics.sample.csv").read_text().splitlines()[0]
T0 = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(days=2)


def forecast(generated: datetime, rpm=100):
    return {"generated_at": iso(generated), "model": "arima-short", "step_minutes": 15,
            "series": [{"timestamp": iso(generated + timedelta(minutes=15 * i)), "requests_per_min": rpm} for i in range(1, 97)]}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Two instances; cluster total 110 rpm one hour after T0 and 100 rpm six hours after. Nothing at 24 h."""
    def line(t, inst, rpm):
        return f"{iso(t)},{inst},t3.micro,{rpm},40,80,30,50,800,6000,3.1,steady"
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    (metrics / "a.csv").write_text("\n".join([HDR, *[line(T0 + timedelta(hours=h), i, rpm)
                                                       for h, rpm in ((1, 55), (6, 50)) for i in ("i-1", "i-2")]]))
    monkeypatch.setenv("ORACLE_SOURCE", "local")
    monkeypatch.setenv("LOCAL_METRICS_DIR", str(metrics))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FORECAST_WINDOW_HOURS", raising=False)
    return LocalStore(tmp_path)


def test_error_per_horizon_and_null_when_actual_missing(env):
    env.put("forecast", forecast(T0))
    out = core.forecast_accuracy(7)
    assert out == {"window_hours": 72, "rows": [{"generated_at": iso(T0), "model": "arima-short",
                                                 "error_pct_1h": 9.09, "error_pct_6h": 0.0, "error_pct_24h": None}]}


def test_fresh_forecast_is_not_scored_yet_and_rows_are_oldest_first(env):
    now = datetime.now(UTC).replace(microsecond=0)
    env.put("forecast", forecast(now))
    env.put("forecast", forecast(T0))
    rows = core.forecast_accuracy(7)["rows"]
    assert [r["generated_at"] for r in rows] == [iso(T0), iso(now)]
    assert rows[1]["error_pct_1h"] is None and rows[1]["error_pct_6h"] is None and rows[1]["error_pct_24h"] is None


def test_forecast_older_than_days_is_left_out_and_no_metrics_is_not_an_error(env, monkeypatch, tmp_path):
    env.put("forecast", forecast(T0))
    assert core.forecast_accuracy(1)["rows"] == []
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("LOCAL_METRICS_DIR", str(empty))
    assert core.forecast_accuracy(7)["rows"][0]["error_pct_1h"] is None


def test_replay_style_forecast_whose_series_is_far_from_generated_at_stays_null(env):
    doc = forecast(T0 - timedelta(days=30))  # series a month before generated_at, as in replay mode
    doc["generated_at"] = iso(T0)
    env.put("forecast", doc)
    assert core.forecast_accuracy(7)["rows"][0]["error_pct_1h"] is None


def test_endpoint(env, monkeypatch):
    monkeypatch.setenv("FORECAST_WINDOW_HOURS", "48")
    env.put("forecast", forecast(T0))
    r = TestClient(api.app).get("/forecast-accuracy", params={"days": 7})
    assert r.status_code == 200 and r.json()["window_hours"] == 48 and r.json()["rows"][0]["error_pct_1h"] == 9.09
    assert TestClient(api.app).get("/forecast-accuracy", params={"days": 0}).status_code == 422


def test_dashboard_draws_the_chart_when_forecasts_are_scored(monkeypatch):
    import client  # the module app.py imports
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ORACLE_API_URL", raising=False)
    monkeypatch.setattr(client, "RECORDED", [])
    monkeypatch.setattr(client.Client, "accuracy", lambda self, days=7: {"window_hours": 48, "rows": [
        {"generated_at": iso(T0), "model": "arima", "error_pct_1h": 4.0, "error_pct_6h": 9.5, "error_pct_24h": None}]})
    st.cache_data.clear()
    before = len(AppTest.from_file("service/dashboard/app.py", default_timeout=60).run().get("plotly_chart"))
    monkeypatch.setattr(client.Client, "accuracy", lambda self, days=7: {"window_hours": 48, "rows": []})
    st.cache_data.clear()
    at = AppTest.from_file("service/dashboard/app.py", default_timeout=60).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == before - 1  # no scored forecast: the chart gives way to a notice
    assert any("No forecast is old enough to score yet" in i.value for i in at.info)
    assert any("last 48 h of data" in c.value for c in at.caption)
    st.cache_data.clear()
