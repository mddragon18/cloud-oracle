# Module 4 — Service, Dashboard & Integration

Turns Modules 2 (`forecast()`) and 3 (`baseline()`/`plan()`) into a running service.
Plan and rules: [`HANDOFF.md`](HANDOFF.md). Session log: [`PROGRESS.md`](PROGRESS.md).

## Setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate      # from repo root
pip install -r service/requirements.txt -r service/requirements-dev.txt -r forecasting/requirements.txt
```

## Run (offline, no AWS)

```bash
make -C service pipeline-once      # sample C1 -> C2 + C3 into data/
make -C service run-api            # http://localhost:8000/docs
make -C service test               # plain-script test + pytest (moto for AWS code)
```

Live local metrics: `make up && make load PATTERN=spike`, then
`service/scripts/pull_local_metrics.sh` and `ORACLE_SOURCE=local make -C service pipeline-once`.

## Dashboard on Streamlit Community Cloud

Cloud runs `streamlit run service/dashboard/app.py` from the repo root and installs only
`service/dashboard/requirements.txt`. With no `ORACLE_API_URL` (secrets or env) it starts in offline mode on the
contract sample data ("Demo data: live API not connected yet"); offline mode never touches AWS.
To check a change the way Cloud will:

```bash
python3.11 -m venv /tmp/cloudvenv && /tmp/cloudvenv/bin/pip install -r service/dashboard/requirements.txt
/tmp/cloudvenv/bin/python service/dashboard/check_cloud.py   # AppTest: every panel, no errors, what-if works
```

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/forecast/latest` | latest C2 (`X-Oracle-Source: sample` if nothing stored yet) |
| GET | `/plan/latest` | latest C3 (same header) |
| POST | `/plan` `{"expected_rpm": 1..1000000}` | fresh what-if C3, not stored |
| GET | `/history?days=7` | `{"plans": [C3...]}` newest first |
| GET | `/metrics/recent?hours=24` | `{"rows": [...]}` C1 aggregated per minute (additive) |
| GET | `/health` | `{"status": "ok"}` |

A C2/C3 that fails `schemas.py` validation returns 502; no metrics returns 503.

## Config (env)

`ORACLE_STORE` local|dynamo · `ORACLE_SOURCE` sample|local|s3 · `LOCAL_METRICS_DIR` · `DATA_DIR` ·
`METRICS_BUCKET` · `RESULTS_TABLE` · `ALERT_TOPIC_ARN` (empty = alerts logged, not sent) ·
`ALERT_WINDOW_MIN` (60) · `LOOKBACK_HOURS` (168, measured back from the newest metric row) ·
`AGGREGATE_MODE` per_minute_total|raw · `AWS_REGION` (ap-south-1) · `DASHBOARD_URL`. See `oracle_service/config.py`.

## Deploy / teardown (AWS, `ap-south-1`, account 149236595048)

Needs `aws configure --profile oracle-m4` (done by the human) and Docker. The Lambda image is built
natively for **arm64** (Apple Silicon) and both functions run on arm64. Names live in `deploy/config.sh`.

```bash
make -C service build                                  # local image only, no AWS
ALERT_EMAILS="a@x.com,b@y.com" make -C service deploy  # deploy/up.sh: idempotent create/update
make -C service smoke                                  # deploy/smoke.sh: every endpoint + what-if 500/5000
EVENT='{"source": "sample"}' make -C service invoke    # pipeline once on the contract sample
EVENT='{"force_alert": true}' make -C service invoke   # one test alert email
make -C service schedule-on   # / schedule-off — 15-min schedule, OFF except integration/demo windows
make -C service down          # deploy/down.sh; KEEP=--keep-data keeps the table + SNS topic
```

`up.sh` creates: ECR `oracle-service` (keeps 1 image), DynamoDB `oracle-results` (on-demand, TTL 30 d),
SNS `oracle-alerts`, IAM `oracle-lambda-role` + `oracle-scheduler-role`, Lambda `oracle-api` (30 s) and
`oracle-pipeline` (120 s), log groups (7-day retention), HTTP API `oracle-api` (5 rps / burst 10), and
schedule `oracle-pipeline-15min` (created **DISABLED**). The metrics bucket is Member 1's and is only read.
