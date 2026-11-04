import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """Every test: offline, temp data dir, fake AWS creds (moto only)."""
    for k, v in {"ORACLE_STORE": "local", "ORACLE_SOURCE": "sample", "DATA_DIR": str(tmp_path),
                 "ALERT_TOPIC_ARN": "", "AWS_ACCESS_KEY_ID": "testing",
                 "AWS_SECRET_ACCESS_KEY": "testing", "AWS_DEFAULT_REGION": "ap-south-1"}.items():
        monkeypatch.setenv(k, v)
    return tmp_path
