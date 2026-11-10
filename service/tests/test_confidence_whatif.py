import time
from datetime import UTC, datetime, timedelta

import pytest

from service.dashboard.app import low_confidence_text
from service.oracle_service import alerts, config, core, engine, pipeline
from service.oracle_service.store import LocalStore, iso


def c2(mape, model="arima"):
    return {"model": model, "accuracy": {"mape_pct": mape, "rmse": 1.0}}


def test_high_mape_is_low_confidence():
    assert alerts.low_confidence(c2(284.36))  # the live ARIMA forecast on 2026-11-10
    assert not alerts.low_confidence(c2(8.0))
    assert not alerts.low_confidence(c2(25.0))  # threshold itself is still normal


def test_threshold_comes_from_config(monkeypatch):
    monkeypatch.setenv("CONFIDENCE_MAX_MAPE", "300")
    assert config.load().confidence_max_mape == 300 and not alerts.low_confidence(c2(284.36))


def test_alerts_skip_high_mape_unless_forced(tmp_path):
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    plan = {"recommendation": "scale_out", "reason": "r", "options": [], "exhaustion_at": iso(now + timedelta(minutes=20))}
    s, cfg = LocalStore(tmp_path), config.load()
    assert alerts.check(plan, s, cfg, now=now, c2=c2(284.36), data_age_minutes=1) == "low_confidence"
    assert alerts.check(plan, s, cfg, now=now, c2=c2(284.36), data_age_minutes=1, force=True) == "logged"


def test_banner_names_the_error():
    assert low_confidence_text(155, 284.36) == "Low confidence: forecast error 284% on held-out data; numbers may be unrealistic"
    assert "simple model" in low_confidence_text(155)


@pytest.fixture
def stored(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ORACLE_SOURCE", "sample")
    pipeline.run_once()
    return tmp_path


def test_pipeline_stores_baseline(stored):
    doc = LocalStore(stored).latest("baseline")
    assert doc["generated_at"] == LocalStore(stored).latest("plan")["generated_at"]
    assert "cpu_pct_per_100_rpm" in doc["baseline"]


def test_whatif_uses_stored_forecast_and_baseline_without_reading_metrics(stored, monkeypatch):
    rows = core.get_source(config.load()).get_rows(168)
    expected = engine.whatif(5000, rows)
    monkeypatch.setattr(core, "get_source", lambda cfg: pytest.fail("what-if re-read the metrics source"))
    t0 = time.monotonic()
    got = core.whatif_plan(5000)
    assert time.monotonic() - t0 < 2
    assert {k: v for k, v in got.items() if k != "generated_at"} == {k: v for k, v in expected.items() if k != "generated_at"}


def test_whatif_falls_back_to_source_when_nothing_stored(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ORACLE_SOURCE", "sample")
    assert core.whatif_plan(500)["peak_requests_per_min"] == 500
