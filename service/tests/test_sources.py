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
def test_s3_cumulative_upload_dedupes_newest_wins():
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="oracle-metrics", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    old = [HDR, line("2026-10-25T10:00:00Z", "i-1", rpm=1)]
    new = [HDR, line("2026-10-25T10:00:00Z", "i-1"), line("2026-10-25T10:01:00Z", "i-1")]
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-1/metrics-20261025T100000Z.csv", Body="\n".join(old))
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-1/metrics-20261025T100100Z.csv", Body="\n".join(new))
    s3.put_object(Bucket="oracle-metrics", Key="metrics/i-2/metrics-20261025T100100Z.csv", Body="\n".join([HDR, line("2026-10-25T10:01:00Z", "i-2")]))
    rows = S3Source("oracle-metrics", "ap-south-1", client=s3).get_rows(168)
    assert len(rows) == 3 and rows[0]["requests_per_min"] == 100


@mock_aws
def test_s3_keeps_every_run_after_collector_restart():
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="oracle-metrics", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    for inst in ("i-1", "i-2"):
        run1 = [HDR, line("2026-11-04T13:00:00Z", inst), line("2026-11-04T13:01:00Z", inst)]
        run2 = [HDR, line("2026-11-05T07:00:00Z", inst), line("2026-11-05T07:01:00Z", inst)]
        s3.put_object(Bucket="oracle-metrics", Key=f"metrics/{inst}/metrics-20261104T130200Z.csv", Body="\n".join(run1))
        s3.put_object(Bucket="oracle-metrics", Key=f"metrics/{inst}/metrics-20261105T070200Z.csv", Body="\n".join(run2))
    rows = S3Source("oracle-metrics", "ap-south-1", client=s3).get_rows(168)
    assert len(rows) == 8
    assert [r["timestamp"] for r in rows] == sorted(r["timestamp"] for r in rows)
    assert {(r["timestamp"][:10], r["instance_id"]) for r in rows} == {
        (d, i) for d in ("2026-11-04", "2026-11-05") for i in ("i-1", "i-2")}
