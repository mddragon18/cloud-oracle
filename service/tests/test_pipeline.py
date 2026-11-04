import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.oracle_service import pipeline
from service.oracle_service.api import app
from service.oracle_service.lambda_handlers import pipeline_handler

c = TestClient(app)


def test_empty_store_serves_samples():
    r = c.get("/plan/latest")
    assert r.status_code == 200 and r.headers["X-Oracle-Source"] == "sample"
    assert c.get("/history").json() == {"plans": []}


def test_end_to_end(env):
    s = pipeline.run_once()
    assert s["rows"] == 2 and (env / "plan.out.json").exists()
    r = c.get("/plan/latest")
    assert r.headers["X-Oracle-Source"] == "live" and r.json()["generated_at"] == s["generated_at"]
    assert c.get("/forecast/latest").status_code == 200
    assert len(c.get("/history?days=7").json()["plans"]) == 1
    assert len(c.get("/metrics/recent?hours=24").json()["rows"]) == 2
    assert c.get("/health").json() == {"status": "ok"}


def test_whatif_validation():
    assert len(c.post("/plan", json={"expected_rpm": 5000}).json()["options"]) == 2
    assert c.post("/plan", json={"expected_rpm": 0}).status_code == 422
    assert c.post("/plan", json={"expected_rpm": 2_000_000}).status_code == 422
    assert not list(Path(os.environ["DATA_DIR"]).glob("plan/*"))


def test_contract_break_is_502(env):
    (env / "plan").mkdir()
    (env / "plan" / "x.json").write_text('{"generated_at": "z"}')
    assert c.get("/plan/latest").status_code == 502


def test_failure_stores_nothing(env, monkeypatch):
    monkeypatch.setenv("ORACLE_SOURCE", "local")
    monkeypatch.setenv("LOCAL_METRICS_DIR", str(env / "none"))
    with pytest.raises(ValueError):
        pipeline_handler({}, None)
    assert not (env / "plan").exists()


def test_force_alert_handler(env):
    assert pipeline_handler({"force_alert": True}, None)["alert"] == "logged"
