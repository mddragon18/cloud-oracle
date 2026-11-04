"""Capacity alerts via SNS, guarded against stale / low-confidence data and de-duplicated via the store's 'alert' kind."""
import json
import logging
from datetime import UTC, datetime, timedelta

from .config import Config
from .sources import parse_ts
from .store import iso

log = logging.getLogger(__name__)
SAME_EXHAUSTION = timedelta(minutes=30)
RESEND_AFTER = timedelta(minutes=60)
STALE_MIN = 30


def low_confidence(c2: dict | None) -> bool:
    """Naive model or no measured accuracy -> numbers may be unrealistic."""
    if not c2:
        return False
    return c2.get("model") == "naive" or (c2.get("accuracy") or {}).get("mape_pct") is None


def alert_kind(c3: dict, now: datetime, window_min: int) -> str | None:
    """'exhaustion' if 0 <= minutes left <= window, 'exceeded' if exhaustion_at is already past, else None."""
    ex = c3.get("exhaustion_at")
    if ex is None:
        return None
    left = parse_ts(ex) - now
    if left < timedelta(0):
        return "exceeded"
    return "exhaustion" if left <= timedelta(minutes=window_min) else None


def is_duplicate(store, exhaustion_at: str | None, now: datetime) -> bool:
    """An alert for an exhaustion_at within ±30 min was sent in the last 60 min."""
    if exhaustion_at is None:
        return False
    ex = parse_ts(exhaustion_at)
    for a in store.since("alert", 1):
        if (a.get("exhaustion_at") and abs(parse_ts(a["exhaustion_at"]) - ex) <= SAME_EXHAUSTION
                and now - parse_ts(a["generated_at"]) <= RESEND_AFTER):
            return True
    return False


def message(c3: dict, dashboard_url: str, kind: str | None = None) -> str:
    ex = c3.get("exhaustion_at")
    head = {"exceeded": f"Capacity already exceeded (forecast crossed the threshold at {ex})",
            "exhaustion": f"Capacity runs out at: {ex}"}.get(kind, f"Forced test alert (exhaustion_at: {ex or 'none'})")
    lines = [head, f"Recommendation: {c3['recommendation']} — {c3['reason']}", ""]
    for o in c3["options"]:
        lines.append(f"- {o['strategy']}: {o['instances']} x {o['instance_type']}, ${o['usd_per_day']}/day")
    if dashboard_url:
        lines += ["", f"Dashboard: {dashboard_url}"]
    return "\n".join(lines)


def send_alert(cfg: Config, subject: str, body: str, client=None) -> bool:
    """Publish to SNS. Returns False (logged, not sent) when ALERT_TOPIC_ARN is empty."""
    if not cfg.alert_topic_arn:
        log.info('{"event": "alert_skipped", "why": "no ALERT_TOPIC_ARN"}')
        return False
    if client is None:
        import boto3
        client = boto3.client("sns", region_name=cfg.aws_region)
    client.publish(TopicArn=cfg.alert_topic_arn, Subject=subject[:100], Message=body)
    return True


def _skip(why: str, msg: str) -> str:
    log.info(json.dumps({"event": "alert_skipped", "why": why, "msg": msg}))
    return why


def check(c3: dict, store, cfg: Config, now: datetime | None = None, force: bool = False, client=None,
          c2: dict | None = None, data_age_minutes: float | None = None) -> str:
    """Alert if needed. Returns 'none' | 'stale' | 'low_confidence' | 'duplicate' | 'sent' | 'logged' (no topic).

    force=True skips every guard (test alert)."""
    now = now or datetime.now(UTC)
    kind = alert_kind(c3, now, cfg.alert_window_min)
    if not force:
        if data_age_minutes is not None and data_age_minutes > STALE_MIN:
            return _skip("stale", "alert skipped: stale data")
        if low_confidence(c2):
            return _skip("low_confidence", "alert skipped: low-confidence forecast (naive model or no accuracy)")
        if kind is None:
            return "none"
        if is_duplicate(store, c3["exhaustion_at"], now):
            return "duplicate"
    subject = {"exceeded": "[oracle] capacity already exceeded",
               "exhaustion": f"[oracle] capacity runs out at {c3.get('exhaustion_at')}"}.get(kind, "[oracle] test alert")
    sent = send_alert(cfg, subject, message(c3, cfg.dashboard_url, None if force else kind), client)
    store.put("alert", {"generated_at": iso(now), "exhaustion_at": c3.get("exhaustion_at"),
                        "kind": "forced" if force else kind, "sent": sent, "forced": force})
    return "sent" if sent else "logged"
