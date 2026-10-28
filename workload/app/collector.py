"""C1 collector: request middleware (count + latency) and psutil host stats.

Writes one C1 row per instance per minute to METERS_PATH (default
workload/data/metrics.csv) and uploads it to S3 every S3_UPLOAD_S seconds when
S3_BUCKET is set. Column definitions: contracts/README.md (C1).
"""
import csv
import os
import re
import socket
import threading
import time
from collections import deque
from datetime import datetime, timezone

import psutil

METRICS_PATH = os.environ.get("METRICS_PATH", "data/metrics.csv")
COLLECT_INTERVAL_S = int(os.environ.get("COLLECT_INTERVAL_S", "60"))
S3_UPLOAD_S = int(os.environ.get("S3_UPLOAD_S", "300"))
INSTANCE_ID = os.environ.get("INSTANCE_ID", socket.gethostname())
INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "t3.micro")
PATTERN = os.environ.get("WORKLOAD_PATTERN", "steady")

COLUMNS = [
    "timestamp", "instance_id", "instance_type", "requests_per_min",
    "avg_latency_ms", "p95_latency_ms", "cpu_pct", "mem_pct",
    "net_in_kb", "net_out_kb", "disk_used_gb", "workload_pattern",
]


class Recorder:
    """Keeps (unix_time, latency_ms) per request for the C1 window stats."""

    def __init__(self):
        self.records = deque()

    def record(self, latency_ms):
        now = time.time()
        self.records.append((now, latency_ms))
        cutoff = now - 3600
        while self.records and self.records[0][0] < cutoff:
            self.records.popleft()

    def window(self, seconds=60):
        cutoff = time.time() - seconds
        latencies = [lat for ts, lat in self.records if ts >= cutoff]
        if not latencies:
            return 0, 0.0, 0.0
        latencies.sort()
        avg = sum(latencies) / len(latencies)
        p95 = latencies[max(0, int(round(len(latencies) * 0.95)) - 1)]
        return len(latencies), avg, p95


RECORDER = Recorder()


def _utc_minute():
    return datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")


class Collector(threading.Thread):
    def __init__(self, path=METRICS_PATH):
        super().__init__(daemon=True)
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(COLUMNS)
        self.last_net = psutil.net_io_counters()
        self.last_upload = 0.0

    def run(self):
        # cpu_percent(None) -> % since the previous call, i.e. over the last minute
        psutil.cpu_percent(interval=None)
        while True:
            time.sleep(COLLECT_INTERVAL_S)
            self._write_row()
            self._maybe_upload()

    def _write_row(self):
        rpm, avg_ms, p95_ms = RECORDER.window(COLLECT_INTERVAL_S)
        net = psutil.net_io_counters()
        row = [
            _utc_minute(),
            INSTANCE_ID,
            INSTANCE_TYPE,
            rpm,
            round(avg_ms, 1),
            round(p95_ms, 1),
            round(psutil.cpu_percent(interval=None), 1),
            round(psutil.virtual_memory().percent, 1),
            round((net.bytes_in - self.last_net.bytes_in) / 1024),
            round((net.bytes_out - self.last_net.bytes_out) / 1024),
            round(psutil.disk_usage("/").used / 2**30, 1),
            PATTERN,
        ]
        self.last_net = net
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(row)

    def _maybe_upload(self):
        bucket = os.environ.get("S3_BUCKET")
        if not bucket or time.time() - self.last_upload < S3_UPLOAD_S:
            return
        try:
            import boto3  # optional until the AWS run
        except ImportError:
            return
        try:
            key = f"metrics/{INSTANCE_ID}/metrics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
            s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
            s3.upload_file(self.path, bucket, key)
            self.last_upload = time.time()
        except Exception as e:
            print(f"[collector] S3 upload failed: {e}", flush=True)


def start_collector():
    Collector().start()
