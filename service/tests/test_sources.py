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


def test_exclude_windows_end_exclusive_on_every_source(tmp_path, monkeypatch, caplog):
    times = ["07:42:00", "07:43:00", "07:52:00", "07:53:00"]
    (tmp_path / "a.csv").write_text("\n".join([HDR, *[line(f"2026-11-05T{t}Z", "a") for t in times]]))
    assert [r["timestamp"][11:19] for r in LocalSource(tmp_path).get_rows(168)] == ["07:42:00", "07:53:00"]
    assert '"dropped": 2' in caplog.text
    monkeypatch.setenv("EXCLUDE_WINDOWS", "")
    assert len(LocalSource(tmp_path).get_rows(168)) == 4


@mock_aws
def test_s3_parallel_read_keeps_newest_file_winning():
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="oracle-metrics", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    for n in range(60):  # more objects than workers
        rows = [HDR, line("2026-10-25T10:00:00Z", "i-1", rpm=n + 1), line(f"2026-10-25T{10 + n // 60}:{n % 60:02d}:30Z", "i-2")]
        s3.put_object(Bucket="oracle-metrics", Key=f"metrics/i-1/metrics-20261025T10{n:04d}Z.csv", Body="\n".join(rows))
    rows = S3Source("oracle-metrics", "ap-south-1", client=s3).get_rows(168)
    assert next(r for r in rows if r["instance_id"] == "i-1")["requests_per_min"] == 60  # last key wins
    assert len(rows) == 61


def bucket_with(files):
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="oracle-metrics", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    for key, ts in files:
        s3.put_object(Bucket="oracle-metrics", Key=key, Body="\n".join([HDR, line(ts, "i-1")]))
    return s3


def kept_timestamps(s3, window_hours, caplog):
    caplog.clear()
    rows = S3Source("oracle-metrics", "ap-south-1", client=s3, window_hours=window_hours).get_rows(10_000)
    return [r["timestamp"] for r in rows], caplog.text


@mock_aws
def test_s3_reads_only_files_inside_the_window_measured_from_newest_file(caplog):
    # Replay case: every file is years older than the wall clock; the window still hangs off the newest file.
    # Newest file 2020-01-05T00:00Z, window 72 h + 1 h -> cutoff 2020-01-01T23:00:00Z, strictly newer is kept.
    s3 = bucket_with([("metrics/i-1/metrics-20200101T000000Z.csv", "2020-01-01T00:00:00Z"),   # 96 h old: skipped
                      ("metrics/i-1/metrics-20200101T230000Z.csv", "2020-01-01T23:00:00Z"),   # exactly on the cutoff: skipped
                      ("metrics/i-1/metrics-20200101T230001Z.csv", "2020-01-01T23:00:01Z"),   # 1 s inside: kept
                      ("metrics/i-1/metrics-20200103T000000Z.csv", "2020-01-03T00:00:00Z"),
                      ("metrics/i-1/metrics-20200105T000000Z.csv", "2020-01-05T00:00:00Z")])  # newest
    ts, logs = kept_timestamps(s3, 72, caplog)
    assert ts == ["2020-01-01T23:00:01Z", "2020-01-03T00:00:00Z", "2020-01-05T00:00:00Z"]
    assert '"kept": 3, "skipped": 2' in logs
    assert len(kept_timestamps(s3, None, caplog)[0]) == 5  # no window: everything


@mock_aws
def test_s3_unparsable_key_falls_back_to_last_modified(caplog):
    # moto stamps LastModified with the real clock, far newer than the 2020 keys
    s3 = bucket_with([("metrics/i-1/metrics-20200101T000000Z.csv", "2020-01-01T00:00:00Z"),
                      ("metrics/i-1/export.csv", "2020-01-01T00:01:00Z"),
                      ("metrics/i-1/metrics-99999999T999999Z.csv", "2020-01-01T00:02:00Z")])
    ts, logs = kept_timestamps(s3, 72, caplog)
    assert ts == ["2020-01-01T00:01:00Z", "2020-01-01T00:02:00Z"] and '"kept": 2, "skipped": 1' in logs


def test_get_source_passes_the_forecast_window(monkeypatch):
    from service.oracle_service import config
    from service.oracle_service.sources import get_source
    monkeypatch.setenv("ORACLE_SOURCE", "s3")
    monkeypatch.setenv("METRICS_BUCKET", "b")
    monkeypatch.setenv("FORECAST_WINDOW_HOURS", "48")
    assert get_source(config.load()).window_hours == 48
