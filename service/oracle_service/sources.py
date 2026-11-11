"""Metrics readers returning C1 rows (floats for numeric columns, like load_metrics)."""
import csv
import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import REPO, Config, load

log = logging.getLogger(__name__)

NUMERIC = ("requests_per_min", "avg_latency_ms", "p95_latency_ms", "cpu_pct",
           "mem_pct", "net_in_kb", "net_out_kb", "disk_used_gb")
S3_READ_WORKERS = 32
KEY_TS = re.compile(r"metrics-(\d{8}T\d{6})Z\.csv$")
SAMPLE_C1 = REPO / "contracts" / "C1-metrics.sample.csv"


class NoMetricsError(ValueError):
    """Not enough metric rows to forecast (empty bucket, empty dir, too-short window)."""


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)  # 3.11+ parses the trailing Z


def parse_csv(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        row = {k: r[k] for k in ("timestamp", "instance_id", "instance_type", "workload_pattern")}
        row.update({k: float(r[k]) for k in NUMERIC})
        rows.append(row)
    return rows


def drop_excluded(rows: list[dict], windows: tuple[str, ...]) -> list[dict]:
    ranges = [tuple(parse_ts(t) for t in w.split("/")) for w in windows]
    kept = [r for r in rows if not any(a <= parse_ts(r["timestamp"]) < b for a, b in ranges)]
    log.warning(json.dumps({"event": "rows_excluded", "dropped": len(rows) - len(kept), "kept": len(kept)}))
    return kept


def finish(rows: list[dict], since_hours: float) -> list[dict]:
    """Dedupe on (timestamp, instance_id), drop excluded windows, keep the lookback window, sort.
    The lookback ends at the newest row."""
    uniq = {(r["timestamp"], r["instance_id"]): r for r in rows}
    rows = sorted(uniq.values(), key=lambda r: (r["timestamp"], r["instance_id"]))
    rows = drop_excluded(rows, load().exclude_windows)
    if rows:
        cutoff = parse_ts(rows[-1]["timestamp"]) - timedelta(hours=since_hours)
        rows = [r for r in rows if parse_ts(r["timestamp"]) >= cutoff]
    if len(rows) < 2:
        raise NoMetricsError(f"need at least 2 C1 rows, got {len(rows)}")
    return rows


class SampleSource:
    def get_rows(self, since_hours: float) -> list[dict]:
        return finish(parse_csv(SAMPLE_C1.read_text()), since_hours)


class LocalSource:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def get_rows(self, since_hours: float) -> list[dict]:
        files = sorted(self.directory.glob("*.csv"))
        if not files:
            raise NoMetricsError(f"no CSV files in {self.directory} (run service/scripts/pull_local_metrics.sh)")
        return finish([r for f in files for r in parse_csv(f.read_text())], since_hours)


class S3Source:
    """Collector layout: metrics/{instance}/metrics-{ts}.csv. Uploads are cumulative only within a run
    and each run restarts the collector, so read every recent object and let finish() dedupe.
    Recent = newer than the newest file minus window_hours + 1 h (measured from the newest file, not the
    wall clock, so replay on old data still works). window_hours None reads everything."""

    def __init__(self, bucket: str, region: str, client=None, window_hours: float | None = None):
        if not bucket:
            raise ValueError("METRICS_BUCKET is not set")
        self.bucket, self.region, self._client, self.window_hours = bucket, region, client, window_hours

    @staticmethod
    def file_time(obj: dict) -> datetime:
        """Upload time from the key's timestamp; LastModified when the key has none."""
        m = KEY_TS.search(obj["Key"])
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            except ValueError:  # digits that aren't a date
                pass
        return obj["LastModified"].astimezone(UTC)

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig
            self._client = boto3.client("s3", region_name=self.region,  # one pooled connection per reader thread
                                        config=BotoConfig(max_pool_connections=S3_READ_WORKERS))
        return self._client

    def get_rows(self, since_hours: float) -> list[dict]:
        files = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix="metrics/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) == 3 and parts[2].endswith(".csv"):
                    files.append((obj["Key"], self.file_time(obj)))
        if not files:
            raise NoMetricsError(f"no metrics/<instance>/*.csv objects in s3://{self.bucket}")
        keys = [k for k, _ in files]
        if self.window_hours is not None:
            cutoff = max(t for _, t in files) - timedelta(hours=self.window_hours + 1)
            keys = [k for k, t in files if t > cutoff]
        log.warning(json.dumps({"event": "s3_files", "kept": len(keys), "skipped": len(files) - len(keys),
                                "window_hours": self.window_hours}))
        client = self.client  # create once, before the threads; boto3 clients are thread-safe

        def read(key: str) -> list[dict]:
            return parse_csv(client.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode())

        # hundreds of small objects: read them in parallel or POST /plan outruns API Gateway's 30 s
        with ThreadPoolExecutor(max_workers=S3_READ_WORKERS) as pool:
            parts = list(pool.map(read, keys))  # map keeps key order, so finish() still lets newer files win
        return finish([r for part in parts for r in part], since_hours)


def get_source(cfg: Config):
    if cfg.source == "sample":
        return SampleSource()
    if cfg.source == "local":
        return LocalSource(cfg.local_metrics_dir)
    if cfg.source == "s3":
        return S3Source(cfg.metrics_bucket, cfg.aws_region, window_hours=cfg.forecast_window_hours)
    raise ValueError(f"unknown ORACLE_SOURCE {cfg.source!r}")
