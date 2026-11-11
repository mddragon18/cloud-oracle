"""All Module 4 env vars in one place (HANDOFF §6)."""
import os
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
# repo checkout: <repo>/service/oracle_service; Lambda image: /var/task/oracle_service with contracts/ beside it
REPO = _HERE.parents[1] if (_HERE.parents[1] / "contracts").is_dir() else _HERE.parents[2]


# Comma-separated UTC start/end ranges, end exclusive. Default: Nov-5 load-tuning rows (Member 1).
DEFAULT_EXCLUDE_WINDOWS = "2026-11-05T07:43:00Z/2026-11-05T07:53:00Z"


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
    forecast_window_hours: int
    aggregate_mode: str
    aws_region: str
    dashboard_url: str
    exclude_windows: tuple[str, ...]
    replay_mode: bool
    confidence_max_mape: float


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
        # Sliding window shared with forecasting/ (Member 2 reads the same variable). The only place the default lives.
        forecast_window_hours=int(e("FORECAST_WINDOW_HOURS") or 72),
        aggregate_mode=e("AGGREGATE_MODE", "raw"),
        aws_region=e("AWS_REGION", "ap-south-1"),
        dashboard_url=e("DASHBOARD_URL", ""),
        exclude_windows=tuple(w.strip() for w in e("EXCLUDE_WINDOWS", DEFAULT_EXCLUDE_WINDOWS).split(",") if w.strip()),
        replay_mode=e("REPLAY_MODE", "0").lower() in ("1", "true", "on"),
        confidence_max_mape=float(e("CONFIDENCE_MAX_MAPE", "25")),  # % error above which a forecast is low confidence
    )
