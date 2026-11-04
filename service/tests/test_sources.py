import boto3
import pytest
from moto import mock_aws

from service.oracle_service.sources import SAMPLE_C1, LocalSource, S3Source

HDR = SAMPLE_C1.read_text().splitlines()[0]


def line(ts, inst, rpm=100):
    return f"{ts},{inst},t3.micro,{rpm},40,80,30,50,800,6000,3.1,steady"


def test_local_dedupe_and_sort(tmp_path):
    (tmp_path / "a.csv").write_text("\n".join([HDR, line("2026-10-25T10:01:00Z", "a"), line("2026-10-25T10:00:00Z", "a")]))
    (tmp_path / "b.csv").write_text("\n".join([HDR, line("2026-10-25T10:00:00Z", "a")]))
    rows = LocalSource(tmp_path).get_rows(168)
    assert [r["timestamp"] for r in rows] == ["2026-10-25T10:00:00Z", "2026-10-25T10:01:00Z"]


def test_too_few_rows(tmp_path):
    (tmp_path / "a.csv").write_text("\n".join([HDR, line("2026-10-25T10:00:00Z", "a")]))
    with pytest.raises(ValueError):
        LocalSource(tmp_path).get_rows(168)


@mock_aws
def test_s3_newest_cumulative_per_instance():
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="oracle-metrics", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    old = [HDR, line("2026-10-25T10:00:00Z", "i-1", rpm=1)]
    new = [HDR, line("2026-10-25T10:00:00Z", "i-1"), line("2026-10-25T10:01:00Z", "i-1")]
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-1/metrics-20261025T100000Z.csv", Body="\n".join(old))
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-1/metrics-20261025T100100Z.csv", Body="\n".join(new))
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-2/metrics-20261025T100100Z.csv", Body="\n".join([HDR, line("2026-10-25T10:01:00Z", "i-2")]))
    rows = S3Source("oracle-metrics", "ap-south-1", client=s3).get_rows(168)
    assert len(rows) == 3 and rows[0]["requests_per_min"] == 100
