"""Metrics readers returning C1 rows (floats for numeric columns, like load_metrics)."""
import csv
import io
from datetime import datetime, timedelta
from pathlib import Path

from .config import REPO, Config

NUMERIC = ("requests_per_min", "avg_latency_ms", "p95_latency_ms", "cpu_pct",
           "mem_pct", "net_in_kb", "net_out_kb", "disk_used_gb")
SAMPLE_C1 = REPO / "contracts" / "C1-metrics.sample.csv"


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_csv(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        row = {k: r[k] for k in ("timestamp", "instance_id", "instance_type", "workload_pattern")}
        row.update({k: float(r[k]) for k in NUMERIC})
        rows.append(row)
    return rows


def finish(rows: list[dict], since_hours: float) -> list[dict]:
    """Dedupe on (timestamp, instance_id), keep the lookback window, sort. Window ends at the newest row."""
    uniq = {(r["timestamp"], r["instance_id"]): r for r in rows}
    rows = sorted(uniq.values(), key=lambda r: (r["timestamp"], r["instance_id"]))
    if rows:
        cutoff = parse_ts(rows[-1]["timestamp"]) - timedelta(hours=since_hours)
        rows = [r for r in rows if parse_ts(r["timestamp"]) >= cutoff]
    if len(rows) < 2:
        raise ValueError(f"need at least 2 C1 rows, got {len(rows)}")
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
            raise ValueError(f"no CSV files in {self.directory} (run service/scripts/pull_local_metrics.sh)")
        return finish([r for f in files for r in parse_csv(f.read_text())], since_hours)


class S3Source:
    """Collector layout: metrics/{instance}/metrics-{ts}.csv, each upload cumulative -> newest per instance."""

    def __init__(self, bucket: str, region: str, client=None):
        if not bucket:
            raise ValueError("METRICS_BUCKET is not set")
        self.bucket, self.region, self._client = bucket, region, client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def get_rows(self, since_hours: float) -> list[dict]:
        newest: dict[str, str] = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix="metrics/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) == 3 and parts[2].endswith(".csv"):
                    # timestamped names sort chronologically
                    newest[parts[1]] = max(newest.get(parts[1], ""), obj["Key"])
        rows = []
        for key in newest.values():
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode()
            rows += parse_csv(body)
        return finish(rows, since_hours)


def get_source(cfg: Config):
    if cfg.source == "sample":
        return SampleSource()
    if cfg.source == "local":
        return LocalSource(cfg.local_metrics_dir)
    if cfg.source == "s3":
        return S3Source(cfg.metrics_bucket, cfg.aws_region)
    raise ValueError(f"unknown ORACLE_SOURCE {cfg.source!r}")
