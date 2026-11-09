import json
from datetime import UTC, datetime, timedelta

import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from service.dashboard.app import replay_text
from service.dashboard.client import Client
from service.oracle_service import alerts, api, config, core, pipeline
from service.oracle_service.config import REPO
from service.oracle_service.store import LocalStore, iso

C2 = json.loads((REPO / "contracts/C2-forecast.sample.json").read_text())
NEWEST = "2026-10-25T10:15:00Z"  # sample's first forecast point minus one step
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("REPLAY_MODE", raising=False)
    assert config.load().replay_mode is False
    q = core.quality(C2)
    assert q["replay_at"] is None and q["data_age_minutes"] > 30 and q["confidence"] == "low"


def test_quality_measures_from_newest_row(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "1")
    q = core.quality(C2, now=datetime.now(UTC))
    assert q["data_age_minutes"] == 0 and q["replay_at"] == NEWEST


def test_replay_never_hides_a_weak_model(monkeypatch):
    monkeypatch.setenv("REPLAY_MODE", "1")
    assert core.quality({**C2, "model": "naive"})["confidence"] == "low"


def test_api_header_only_in_replay(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("REPLAY_MODE", raising=False)
    assert "x-oracle-replay-at" not in TestClient(api.app).get("/forecast/latest").headers
    monkeypatch.setenv("REPLAY_MODE", "1")
    h = TestClient(api.app).get("/forecast/latest").headers
    assert h["x-oracle-replay-at"] == NEWEST and h["x-oracle-data-age-minutes"] == "0"


def test_pipeline_alert_clock_is_newest_row(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REPLAY_MODE", "1")
    seen = {}
    monkeypatch.setattr(pipeline.alerts, "check", lambda *a, **k: seen.update(k) or "none")
    out = pipeline.run_once()
    assert out["data_age_minutes"] == 0 and iso(seen["now"]) == "2026-10-25T10:01:00Z" and seen["data_age_minutes"] == 0


def test_replayed_alert_still_dedupes(tmp_path):
    s, ex = LocalStore(tmp_path), iso(LONG_AGO + timedelta(minutes=30))
    s.put("alert", {"generated_at": iso(LONG_AGO), "exhaustion_at": ex})
    assert alerts.is_duplicate(s, ex, LONG_AGO)


def test_client_reads_replay_header(monkeypatch):
    c = Client("http://x")
    monkeypatch.setattr(c, "_http", lambda *a: (C2, {"X-Oracle-Replay-At": NEWEST, "X-Oracle-Confidence": "low"}))
    assert c.forecast()[2]["replay_at"] == NEWEST


def test_badge_shown_only_in_replay(monkeypatch):
    assert replay_text(None) is None and replay_text(NEWEST) == "Replay of recorded run (2026-10-25)"
    monkeypatch.delenv("ORACLE_API_URL", raising=False)
    monkeypatch.delenv("REPLAY_MODE", raising=False)
    import client  # embedded mode always replays, so test the badge on the sample path
    monkeypatch.setattr(client, "RECORDED", [])
    badge = lambda at: any("Replay of recorded run" in m.value for m in at.markdown)  # noqa: E731
    assert not badge(AppTest.from_file("service/dashboard/app.py", default_timeout=60).run())
    monkeypatch.setenv("REPLAY_MODE", "1")
    st.cache_data.clear()
    at = AppTest.from_file("service/dashboard/app.py", default_timeout=60).run()
    assert not at.exception and badge(at)
