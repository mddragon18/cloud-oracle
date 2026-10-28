# Contracts — frozen formats (C1–C3)

Frozen on day one. A change needs a message in the team group and agreement from
 whoever reads that file. Every module is tested against these sample files, so it
works with the real data the first time it arrives.

| Contract | File | Written by | Read by |
|---|---|---|---|
| C1 | `C1-metrics.sample.csv` | Module 1 (collector → S3) | Modules 2, 3 |
| C2 | `C2-forecast.sample.json` | Module 2 `forecast()` | Module 3, Module 4 |
| C3 | `C3-plan.sample.json` | Module 3 `plan()` | Module 4 (stores and serves) |

## C1 — metrics.csv

One row per instance per minute. Times in UTC ISO 8601.

| Column | Meaning |
|---|---|
| `timestamp` | UTC ISO 8601, minute of the row |
| `instance_id` | EC2 instance id / container name |
| `instance_type` | e.g. `t3.micro` |
| `requests_per_min` | requests to this instance in the last minute |
| `avg_latency_ms` | average handler latency over that minute |
| `p95_latency_ms` | 95th percentile latency |
| `cpu_pct` | host CPU % (psutil) |
| `mem_pct` | host memory % |
| `net_in_kb` / `net_out_kb` | network counters since last row |
| `disk_used_gb` | disk used on the data volume |
| `workload_pattern` | `steady` / `cycle` / `spike` / `growth` |

## C2 — forecast.json

`forecast(metrics_df) -> dict` output. `horizon_minutes` / `step_minutes`: the
series. `accuracy`: MAPE % and RMSE on a held-out day. `lower`/`upper`: the
uncertainty band. `exhaustion_at`: when cpu_pct crosses `cpu_threshold_pct`.

## C3 — plan.json

`plan(forecast, baseline) -> dict` output. `options[]`: the scale-out vs scale-up
comparisons; `recommendation` + `reason`: the engine's pick. Prices in these
samples are **placeholders** — Module 3 fills real ones from the Price List cache.

## API surface (Module 4)

| Method | Path | Returns |
|---|---|---|
| GET | `/forecast/latest` | latest C2 |
| GET | `/plan/latest` | latest C3 |
| POST | `/plan` `{"expected_rpm": 5000}` | fresh C3 for that what-if load |
| GET | `/history?days=7` | past plans, for the dashboard |
| GET | `/health` | `{"status": "ok"}` |
