"""All Module 4 env vars in one place (HANDOFF §6)."""
import os
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else REPO / p


@dataclass(frozen=True)
class Config:
    store: str
    source: str
    local_metrics_dir: Path
    data_dir: Path
    metrics_bucket: str
    results_table: str
    alert_topic_arn: str
    alert_window_min: int
    lookback_hours: int
    aggregate_mode: str
    aws_region: str
    dashboard_url: str


def load() -> Config:
    """Read env now (cheap; lets tests change env between calls)."""
    e = os.environ.get
    return Config(
        store=e("ORACLE_STORE", "local"),
        source=e("ORACLE_SOURCE", "sample"),
        local_metrics_dir=_path(e("LOCAL_METRICS_DIR", "data/local-metrics")),
        data_dir=_path(e("DATA_DIR", "data")),
        metrics_bucket=e("METRICS_BUCKET", ""),
        results_table=e("RESULTS_TABLE", "oracle-results"),
        alert_topic_arn=e("ALERT_TOPIC_ARN", ""),
        alert_window_min=int(e("ALERT_WINDOW_MIN", "60")),
        lookback_hours=int(e("LOOKBACK_HOURS", "168")),
        aggregate_mode=e("AGGREGATE_MODE", "per_minute_total"),
        aws_region=e("AWS_REGION", "ap-south-1"),
        dashboard_url=e("DASHBOARD_URL", ""),
    )
