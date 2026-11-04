import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import boto3
from moto import mock_aws

from service.oracle_service import alerts, config
from service.oracle_service.config import REPO
from service.oracle_service.store import LocalStore, iso

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def c3(ex):
    p = json.loads((REPO / "contracts/C3-plan.sample.json").read_text())
    p["exhaustion_at"] = ex
    return p


def test_null_and_far_no_alert(tmp_path):
    cfg, s = config.load(), LocalStore(tmp_path)
    assert alerts.check(c3(None), s, cfg, now=NOW) == "none"
    assert alerts.check(c3(iso(NOW + timedelta(hours=3))), s, cfg, now=NOW) == "none"


def test_within_window_then_duplicate(tmp_path):
    cfg, s = config.load(), LocalStore(tmp_path)
    assert alerts.check(c3(iso(NOW + timedelta(minutes=30))), s, cfg, now=NOW) == "logged"
    later = NOW + timedelta(minutes=15)
    assert alerts.check(c3(iso(NOW + timedelta(minutes=40))), s, cfg, now=later) == "duplicate"
    assert alerts.check(c3(iso(NOW + timedelta(minutes=30))), s, cfg, now=NOW + timedelta(minutes=61)) == "logged"


@mock_aws
def test_sns_publish(tmp_path):
    sns = boto3.client("sns", region_name="ap-south-1")
    cfg = replace(config.load(), alert_topic_arn=sns.create_topic(Name="oracle-alerts")["TopicArn"])
    assert alerts.check(c3(None), LocalStore(tmp_path), cfg, now=NOW, force=True, client=sns) == "sent"


def c2(model="arima", mape=8.4):
    return {"model": model, "accuracy": {"mape_pct": mape, "rmse": 1.0 if mape is not None else None}}


def test_stale_data_skips(tmp_path, caplog):
    import logging
    caplog.set_level(logging.INFO)
    s = LocalStore(tmp_path)
    r = alerts.check(c3(iso(NOW + timedelta(minutes=10))), s, config.load(), now=NOW, c2=c2(), data_age_minutes=31)
    assert r == "stale" and "alert skipped: stale data" in caplog.text and not (tmp_path / "alert").exists()


def test_low_confidence_skips_unless_forced(tmp_path):
    s, cfg, ex = LocalStore(tmp_path), config.load(), iso(NOW + timedelta(minutes=10))
    assert alerts.check(c3(ex), s, cfg, now=NOW, c2=c2("naive", None), data_age_minutes=1) == "low_confidence"
    assert alerts.check(c3(ex), s, cfg, now=NOW, c2=c2("arima", None), data_age_minutes=1) == "low_confidence"
    assert alerts.check(c3(ex), s, cfg, now=NOW, c2=c2("naive", None), data_age_minutes=99, force=True) == "logged"


def test_window_bounds(tmp_path):
    s, cfg = LocalStore(tmp_path), config.load()
    assert alerts.alert_kind(c3(iso(NOW)), NOW, 60) == "exhaustion"
    assert alerts.alert_kind(c3(iso(NOW + timedelta(minutes=60))), NOW, 60) == "exhaustion"
    assert alerts.alert_kind(c3(iso(NOW + timedelta(minutes=61))), NOW, 60) is None
    assert alerts.alert_kind(c3(iso(NOW - timedelta(minutes=1))), NOW, 60) == "exceeded"
    assert alerts.check(c3(iso(NOW + timedelta(minutes=61))), s, cfg, now=NOW, c2=c2(), data_age_minutes=1) == "none"


def test_exceeded_alert_once_when_fresh(tmp_path):
    s, cfg, ex = LocalStore(tmp_path), config.load(), iso(NOW - timedelta(minutes=45))
    assert alerts.check(c3(ex), s, cfg, now=NOW, c2=c2(), data_age_minutes=5) == "logged"
    assert alerts.check(c3(ex), s, cfg, now=NOW + timedelta(minutes=15), c2=c2(), data_age_minutes=5) == "duplicate"
    assert s.latest("alert")["kind"] == "exceeded"
    assert "already exceeded" in alerts.message(c3(ex), "", "exceeded")


def test_exceeded_but_stale_no_alert(tmp_path):
    ex = iso(NOW - timedelta(minutes=45))
    assert alerts.check(c3(ex), LocalStore(tmp_path), config.load(), now=NOW, c2=c2(), data_age_minutes=60) == "stale"
