# Module 1 — cloud infrastructure and workload (Member 1)

FastAPI sample app (3 endpoints of different weight) + C1 collector + Locust
patterns + Docker Compose (app x 3 behind nginx) + AWS scripts in `../infra/`.

## Local demo

```bash
make up        # from the repo root: app x 3 + nginx at http://localhost:8090
make load PATTERN=steady   # or cycle | spike | growth
make down
```

Each container writes C1 rows to its own `/data` volume (`docker compose
exec app1 cat /data/metrics.csv`). Combine per instance later in S3.

## Endpoints

| Path | Weight | Purpose |
|---|---|---|
| `GET /` | 5 | light page |
| `GET /compute?n=…` | 1 | CPU-heavy calculation |
| `GET /download?kb=…` | 1 | ~4 MB download |

## Phase II AWS run (2 h, steady + spike)

1. `aws s3 cp contracts/C1-metrics.sample.csv s3://<bucket>/contracts/` (bucket
   created by Member 1 during the run; tag `project=oracle`).
2. t3.micro instance runs the container with `INSTANCE_ID=i-01`,
   `S3_BUCKET=<bucket>` — collector uploads every 5 min.
3. Locust from another t3.micro: `PATTERN=steady` 1 h, then `PATTERN=spike`.
4. Pull the two hours of real metrics.csv from S3 — that is Phase II's deliverable.

## Phase III

`infra/` scripts (make up / make down): Auto Scaling Group + ALB; vertical runs
t3.micro → t3.small → t3.medium and horizontal runs 1 → 5 under the same load;
reactive baseline with target-tracking autoscaling.
