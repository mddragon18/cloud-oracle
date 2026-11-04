import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_metrics_df():
    records = []
    for i in range(2):
        for m in range(5):
            records.append({
                "timestamp": f"2026-10-25T10:{m:02d}:00Z",
                "instance_id": f"i-{i+1:02d}",
                "instance_type": "t3.micro",
                "requests_per_min": 500 + (i * 50),
                "avg_latency_ms": 42.0,
                "p95_latency_ms": 88.0,
                "cpu_pct": 35.0,
                "mem_pct": 52.0,
                "net_in_kb": 820.0,
                "net_out_kb": 6400.0,
                "disk_used_gb": 3.1,
                "workload_pattern": "steady",
            })
    return pd.DataFrame(records)
