"""Capacity-exhaustion alerts via SNS, de-duplicated through the store's 'alert' kind."""
import logging
from datetime import UTC, datetime, timedelta

from .config import Config
from .sources import parse_ts
from .store import iso

log = logging.getLogger(__name__)
SAME_EXHAUSTION = timedelta(minutes=30)
RESEND_AFTER = timedelta(minutes=60)


def should_alert(c3: dict, now: datetime, window_min: int) -> bool:
    """True if exhaustion_at is set and falls within window_min of now (past-due counts)."""
    ex = c3.get("exhaustion_at")
    return ex is not None and parse_ts(ex) - now <= timedelta(minutes=window_min)


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


def message(c3: dict, dashboard_url: str) -> str:
    lines = [f"Capacity runs out at: {c3.get('exhaustion_at') or 'not forecast (forced test alert)'}",
             f"Recommendation: {c3['recommendation']} — {c3['reason']}", ""]
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


def check(c3: dict, store, cfg: Config, now: datetime | None = None, force: bool = False, client=None) -> str:
    """Alert if needed. Returns 'none' | 'duplicate' | 'sent' | 'logged' (no topic configured)."""
    now = now or datetime.now(UTC)
    if not force:
        if not should_alert(c3, now, cfg.alert_window_min):
            return "none"
        if is_duplicate(store, c3["exhaustion_at"], now):
            return "duplicate"
    sent = send_alert(cfg, f"[oracle] capacity runs out at {c3.get('exhaustion_at')}",
                      message(c3, cfg.dashboard_url), client)
    store.put("alert", {"generated_at": iso(now), "exhaustion_at": c3.get("exhaustion_at"),
                        "sent": sent, "forced": force})
    return "sent" if sent else "logged"
