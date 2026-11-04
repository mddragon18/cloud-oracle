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
