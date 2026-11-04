# HANDOFF — Module 4 (Service, Dashboard & Integration)

**Project:** Cloud Cost & Capacity Oracle — "Predict Before You Scale"
**Repo:** https://github.com/mddragon18/cloud-oracle (public)
**You are:** the coding agent working for **Member 4**. You build, test and deploy Module 4 and keep the shared repo healthy.
**Baseline commit when this was written:** `e9e2ff7` ("Scaffold repo: contracts C1-C3, Module 1 app+collector+Locust patterns, module stubs")
**Final deadline:** Phase III evaluation, **15 Dec 2026**. Integration on AWS runs **22 Nov – 5 Dec**.

Read this whole file before writing any code. Then follow §13 (session protocol) every session.

---

## 1. Mission and definition of done

The Oracle watches a cloud app's metrics, forecasts load, and recommends how much infrastructure is needed, when, and at what cost (scale-out vs scale-up). Four modules, one per team member, joined only by three frozen files (C1, C2, C3).

**Module 4 turns Modules 2 and 3 into a running service:**

1. A REST API (FastAPI) with the 5 contract endpoints.
2. A scheduled pipeline: every 15 min, read the latest metrics → `forecast()` → `baseline()` + `plan()` → store results → email an alert if capacity runs out within 60 min.
3. A Streamlit dashboard: forecast vs actual, exhaustion countdown, scale-out vs scale-up cost cards, a what-if box, plan history.
4. Deployment on AWS (Lambda container image + API Gateway HTTP API + DynamoDB + EventBridge Scheduler + SNS), with a one-command teardown. Dashboard on Streamlit Community Cloud.
5. Repo health: README, GitHub Actions CI running `make test`, integration runs on Tue/Sat.

**Done means all of these are true:**

- [ ] `make test` passes locally and in GitHub Actions on every PR to `main`.
- [ ] Everything works fully **offline** (`ORACLE_STORE=local`, `ORACLE_SOURCE=local`) with no AWS credentials.
- [ ] The deployed API answers all 5 endpoints from a public URL; `POST /plan` returns a valid C3 for any `expected_rpm`.
- [ ] The EventBridge schedule writes a new forecast + plan to DynamoDB every 15 min (visible in `/history`).
- [ ] An SNS email arrives when `exhaustion_at` is within 60 min (tested by forcing it), and is not re-sent every 15 min.
- [ ] The public Streamlit dashboard shows all five panels against the deployed API, and degrades cleanly (no stack traces) when the API is down or fields are `null`.
- [ ] `make -C service down` removes every Module 4 AWS resource except what §9 says to keep.
- [ ] `service/README.md` documents setup, run, deploy, teardown; `docs/module4.md` has the report material (§8, W7).

---

## 2. Project context (only what you need)

- Course project, 4 students, **must cost $0**. AWS account is on the **Free plan** (cannot be charged; ~$200 credits; expires ~6 months after creation). A **$1 budget alert** is live. Still treat every resource as if it costs money.
- Region **`ap-south-1`** only. Tag **every** resource `project=oracle`.
- Modules and owners:

| Folder | Module | Owner |
|---|---|---|
| `contracts/` | C1–C3 samples + schema notes | Member 4 (everyone reviews changes) |
| `workload/`, `infra/` | 1 — app, collector, Locust, AWS experiment infra | Member 1 |
| `forecasting/` | 2 — `load_metrics()`, `forecast()` | Member 2 |
| `capacity/` | 3 — `baseline()`, `plan()`, `pricing.json` | Member 3 |
| `service/` | 4 — API, pipeline, dashboard, deploy | **Member 4 (you)** |
| `.github/`, root `README.md`, `docs/` | shared repo health | Member 4 |

---

## 3. Current repo state (verified by reading commit `e9e2ff7`)

```
cloud-oracle/
├── Makefile                 # up / down / load / test  (comment says :8080, real port is :8090)
├── README.md                # basic; Member 4 polishes
├── contracts/
│   ├── README.md            # schema notes + API surface
│   ├── C1-metrics.sample.csv   # only 2 rows
│   ├── C2-forecast.sample.json
│   └── C3-plan.sample.json
├── forecasting/forecast.py  # STUB: load_metrics(path)->list[dict], forecast(rows)->C2 dict (naive linear trend)
├── capacity/plan.py         # STUB: baseline(rows)->dict, plan(c2, base)->C3 dict (PLACEHOLDER prices)
├── service/
│   ├── api/app.py           # STUB: plain functions + FastAPI app; reads samples or data/*.out.json
│   ├── requirements.txt     # fastapi 0.115.*, uvicorn 0.32.*, pydantic 2.*
│   └── tests/test_api.py    # plain-script test, run by `make test`
├── workload/                # Member 1: FastAPI app + collector + Locust + docker-compose (app x3 + nginx on :8090)
├── infra/README.md          # Member 1, Phase III scripts not written yet
└── data/.gitkeep
```

Facts that matter to you:

- **Tests are plain scripts**, run with `python3 <file>` from `make test` (no pytest needed). Keep `service/tests/test_api.py` runnable this way; you may additionally add pytest-style tests.
- **Stub signatures are list-of-dicts, not pandas.** `load_metrics(path)` returns `list[dict]` with numeric fields as `float`. `forecast(rows)` and `baseline(rows)` take that list. The work plan said `forecast(metrics_df)`; Member 2 may switch to a DataFrame later. **Call Modules 2/3 only through one adapter file** (`service/oracle_service/engine.py`, §6) so a signature change is a one-file fix.
- `forecast()` may return `"exhaustion_at": null`. Every consumer (API, alerts, dashboard) must handle `null`.
- `service/api/app.py::history()` computes a cutoff but **never applies it** — bug, fix it.
- `whatif_plan()` adds a non-contract key `peak_override` to the C2 dict before calling `plan()`. Harmless but keep it internal (never store or return that C2).
- **Collector S3 layout (Member 1):** key `metrics/{INSTANCE_ID}/metrics-{YYYYMMDDTHHMMSSZ}.csv`. **Each upload is the whole cumulative CSV for that instance**, not a 5-minute slice. So: for each instance prefix take only the **newest** object, concatenate across instances, de-duplicate on `(timestamp, instance_id)`, sort by `timestamp`.
- Bucket name is not in the repo. Read it from env `METRICS_BUCKET`; ask Member 1 for the value (§12).
- Local metrics: each Docker container writes `/data/metrics.csv` in its own volume (`docker compose -f workload/docker-compose.yml exec app1 cat /data/metrics.csv`).

---

## 4. Hard rules (never break these)

1. **Never commit secrets.** AWS keys live only in a local `.env` (gitignored) or an AWS CLI profile, and in GitHub Actions secrets if ever needed. Never print keys in logs, test output, PR text, or this repo's docs. If you see a key anywhere in the repo or a diff, stop and tell the human.
2. **Never change C1/C2/C3 formats** (`contracts/*.sample.*`, `contracts/README.md` schemas). If you think a change is needed, write it up in `service/PROGRESS.md` under "Needs team decision" and stop on that item.
3. **Stay in your folders:** `service/`, `.github/`, `docs/`, root `README.md`, `contracts/README.md` (wording only). Any edit to `workload/`, `infra/`, `forecasting/`, `capacity/`, or the root `Makefile` goes in a **separate small PR** that names the owner for review. Never "fix" another module's logic yourself — open an issue or note it.
4. **Branches:** `m4-<topic>` → PR into `main`. `main` must always pass `make test`. No force-push to `main`.
5. **AWS:** region `ap-south-1`; tag `project=oracle` on everything that supports tags; create resources only through scripts in `service/deploy/`; every script has a matching teardown. Never create NAT gateways, load balancers, EC2, RDS, or provisioned-capacity anything from Module 4.
6. **Offline first.** Every feature must work with `ORACLE_STORE=local` and `ORACLE_SOURCE=local` before you touch AWS. Tests never call real AWS (use `moto`).
7. **Python 3.11.** Pin dependency versions (§7). Do not add a dependency that is not in §7 without writing why in `PROGRESS.md`.
8. Don't build features not listed here (no auth system, no user accounts, no extra databases, no React frontend).

---

## 5. Contracts cheat sheet

Full definitions: `contracts/README.md`. Summary:

- **C1 `metrics.csv`** — one row per instance per minute: `timestamp, instance_id, instance_type, requests_per_min, avg_latency_ms, p95_latency_ms, cpu_pct, mem_pct, net_in_kb, net_out_kb, disk_used_gb, workload_pattern`. UTC ISO 8601 with `Z`.
- **C2 `forecast.json`** — `generated_at, model, horizon_minutes, step_minutes, accuracy{mape_pct, rmse}, series[{timestamp, requests_per_min, cpu_pct, mem_pct, lower, upper}], cpu_threshold_pct, exhaustion_at (nullable)`.
- **C3 `plan.json`** — `generated_at, peak_requests_per_min, current{instances, instance_type, usd_per_hour}, options[2]{strategy: scale_out|scale_up, instances, instance_type, usd_per_hour, usd_per_day, expected_latency_ms, single_point_of_failure}, bandwidth_mbps, storage_gb_30d, recommendation, reason, exhaustion_at (nullable)`.
- **API surface (Module 4 owns, listed in contracts/README.md):**

| Method | Path | Returns |
|---|---|---|
| GET | `/forecast/latest` | latest C2 |
| GET | `/plan/latest` | latest C3 |
| POST | `/plan` body `{"expected_rpm": int}` | fresh C3 for that load (not stored) |
| GET | `/history?days=7` | `{"plans": [C3, ...]}` newest first, within `days` |
| GET | `/health` | `{"status": "ok"}` |

**One additive endpoint is allowed** because the dashboard needs "actual" values for the forecast-vs-actual chart: `GET /metrics/recent?hours=24` → `{"rows": [C1 rows aggregated per minute]}`. It does not change any contract file, but **post a one-line note in the team group** and add it to the API table in `contracts/README.md`.

Validation: add `service/oracle_service/schemas.py` with Pydantic models for C2 and C3 that mirror the samples exactly (extra keys allowed on input, `exhaustion_at: str | None`). Validate every C2/C3 before storing or returning. A failed validation is logged and returns HTTP 502 with a short message — it means another module broke the contract.

---

## 6. Target layout for Module 4

Restructure `service/` to this (keep `service/api/app.py` as a thin shim that re-exports the app and the old function names so the existing test and `make test` keep working):

```
service/
├── HANDOFF.md                 # this file
├── PROGRESS.md                # session bridge (§13) — create it
├── README.md                  # setup / run / deploy / teardown
├── requirements.txt           # API + pipeline runtime (§7)
├── requirements-dev.txt       # pytest, moto, ruff
├── Makefile                   # run-api, run-dash, pipeline-once, test, build, deploy, down
├── api/
│   └── app.py                 # SHIM: from service.oracle_service.api import app, latest_forecast, ...
├── oracle_service/
│   ├── __init__.py
│   ├── config.py              # all env vars, defaults, one place
│   ├── schemas.py             # Pydantic C2/C3 (+ API request/response models)
│   ├── engine.py              # THE ONLY place that imports forecasting/ and capacity/
│   ├── sources.py             # metrics readers: LocalSource (CSV files / docker), S3Source
│   ├── store.py               # results store: LocalStore (data/ JSON files), DynamoStore
│   ├── pipeline.py            # run_once(): source -> engine -> store -> alerts
│   ├── alerts.py              # should_alert(), send_alert() via SNS, de-duplication
│   ├── api.py                 # FastAPI app (routes call engine/store, never boto3 directly)
│   └── lambda_handlers.py     # api_handler = Mangum(app); pipeline_handler(event, ctx)
├── dashboard/
│   ├── app.py                 # Streamlit entry point
│   ├── client.py              # API client (requests) + offline fallback to oracle_service
│   └── requirements.txt       # streamlit, requests, plotly, pandas (Streamlit Cloud reads this)
├── deploy/
│   ├── Dockerfile.lambda      # FROM public.ecr.aws/lambda/python:3.11
│   ├── config.sh              # names, region, tags (sourced by the scripts)
│   ├── up.sh                  # idempotent create/update of all Module 4 AWS resources
│   ├── down.sh                # deletes them (keeps nothing unless flagged)
│   └── smoke.sh               # curls every endpoint of the deployed API
├── scripts/
│   ├── pull_local_metrics.sh  # copy /data/metrics.csv out of app1..3 into data/local-metrics/
│   └── integrate.sh           # Tue/Sat integration run (§10)
└── tests/
    ├── test_api.py            # existing plain-script test (keep passing)
    ├── test_engine.py
    ├── test_store.py          # LocalStore + DynamoStore via moto
    ├── test_sources.py        # LocalSource + S3Source via moto (cumulative-file dedupe)
    ├── test_pipeline.py
    └── test_alerts.py
```

### Key module responsibilities

**`config.py`** — reads env once:

| Env var | Default | Meaning |
|---|---|---|
| `ORACLE_STORE` | `local` | `local` or `dynamo` |
| `ORACLE_SOURCE` | `sample` | `sample` (contracts C1), `local` (CSV dir), `s3` |
| `LOCAL_METRICS_DIR` | `data/local-metrics` | CSVs for `local` source |
| `DATA_DIR` | `data` | LocalStore output |
| `METRICS_BUCKET` | — | S3 bucket with `metrics/` prefix (from Member 1) |
| `RESULTS_TABLE` | `oracle-results` | DynamoDB table |
| `ALERT_TOPIC_ARN` | — | SNS topic; alerts disabled if empty |
| `ALERT_WINDOW_MIN` | `60` | alert if exhaustion within this many minutes |
| `LOOKBACK_HOURS` | `168` | how much metric history to feed `forecast()` |
| `AGGREGATE_MODE` | `per_minute_total` | how C1 rows are combined before `forecast()` (§12 Q1) |
| `AWS_REGION` | `ap-south-1` | |

**`engine.py`** — wraps the other modules:

```python
def run_forecast(rows: list[dict]) -> dict        # -> validated C2
def run_baseline(rows: list[dict]) -> dict
def run_plan(c2: dict, base: dict) -> dict        # -> validated C3
def whatif(expected_rpm: int, rows: list[dict]) -> dict  # copy C2, set every series rpm = expected_rpm, -> C3
def aggregate(rows, mode) -> list[dict]           # see §12 Q1
```
If Modules 2/3 change signatures (e.g. DataFrame), only this file changes. Use deep copies — never mutate a C2 that is stored or returned.

**`sources.py`** — `get_rows(since_hours) -> list[dict]` in C1 shape (floats for numeric columns, same as `load_metrics`). `S3Source`: `list_objects_v2` under `metrics/` (paginate), newest key per instance prefix, download, parse, dedupe `(timestamp, instance_id)`, drop rows older than the lookback, sort. Raise a clear error if < 2 rows.

**`store.py`** — same interface for both backends:

```python
put(kind: str, doc: dict) -> None          # kind in {"forecast", "plan", "alert"}
latest(kind: str) -> dict | None
since(kind: str, days: int) -> list[dict] # newest first
```
- `LocalStore`: `data/<kind>/<generated_at>.json` plus `data/forecast.out.json` / `data/plan.out.json` for backward compatibility with the stub.
- `DynamoStore`: table `oracle-results`, **PK `kind` (S), SK `generated_at` (S)**, attribute **`body` = JSON string** (avoids float→Decimal problems), `ttl` (N, epoch seconds, now + 30 days). `latest` = Query `ScanIndexForward=False, Limit=1`. `since` = Query with `generated_at >= cutoff_iso`.
- If the store is empty, `latest()` falls back to the contract samples so a fresh deployment still renders (mark the response header `X-Oracle-Source: sample`).

**`pipeline.py`** — `run_once() -> dict` summary: rows = source.get_rows → c2 = run_forecast(aggregate(rows)) → base = run_baseline(rows) → c3 = run_plan(c2, base) → store.put both → alerts.check(c3). Log one JSON line with timings and outcome. Any exception: log it, store nothing partial, re-raise (so Lambda marks the run failed).

**`alerts.py`** — alert when `exhaustion_at` is not null and is within `ALERT_WINDOW_MIN` of now. De-dupe: store an `alert` doc keyed by its `exhaustion_at`; skip if an alert for an `exhaustion_at` within ±30 min was sent in the last 60 min. Email body: plain text — when capacity runs out, recommendation, both options with $/day, dashboard link.

**`api.py`** — the 5 routes (+ `/metrics/recent`), CORS allow `*` for GET only, request validation via Pydantic (`expected_rpm`: int, 1 ≤ value ≤ 1,000,000). `POST /plan` uses the **current** metrics source for the baseline, never stores its result.

**`lambda_handlers.py`** — `api_handler = Mangum(app, lifespan="off")`; `pipeline_handler(event, context)` calls `run_once()` and returns its summary.

---

## 7. Locked tech stack

| Area | Choice | Version pin |
|---|---|---|
| Language | Python | 3.11 |
| API | FastAPI / Uvicorn / Pydantic | `fastapi==0.115.*`, `uvicorn==0.32.*`, `pydantic==2.*` (already in repo) |
| Lambda adapter | Mangum | `mangum>=0.17,<1` |
| AWS SDK | boto3 | `boto3>=1.34,<2` |
| Dashboard | Streamlit + Plotly + pandas + requests | `streamlit==1.38.*`, `plotly>=5.20,<6`, `pandas>=2.1,<3`, `requests>=2.31,<3` |
| Tests | pytest, moto | `pytest>=8,<9`, `moto[s3,dynamodb,sns]>=5,<6` (moto 5 uses `mock_aws`) |
| Lint | ruff | `ruff>=0.5` (dev only, CI warns, does not block) |
| Lambda image | AWS base image | `public.ecr.aws/lambda/python:3.11` |
| IaC | AWS CLI v2 bash scripts | no Terraform/SAM/CDK for Module 4 |
| CI | GitHub Actions | `actions/checkout@v4`, `actions/setup-python@v5` |

The Lambda image must also install `forecasting/requirements.txt` and `capacity/requirements.txt` (copy those folders into the image). **Keep the image under ~500 MB**: no TensorFlow in Lambda unless Member 2 confirms the LSTM must run there; if so, ask them for a lighter inference path (e.g. exported weights) — raise it, don't decide alone.

---

## 8. Work plan (do in order; one PR per work package)

Target dates assume integration starts 22 Nov.

### W0 — Setup (no code changes)
1. Clone, `python3.11 -m venv .venv && source .venv/bin/activate`.
2. `pip install -r service/requirements.txt -r forecasting/requirements.txt` then `make test` → expect three "OK" lines.
3. Read `contracts/README.md`, the three stubs, `workload/app/collector.py`.
4. Create `service/PROGRESS.md` (template in §13). Commit on `m4-setup`.

**Accept:** `make test` green locally; PROGRESS.md exists.

### W1 — Repo health + CI (target: 7 Nov)
1. `.github/workflows/ci.yml`: on `push` to `main` and `pull_request`; Ubuntu, Python 3.11, pip cache; install `service/requirements.txt`, `service/requirements-dev.txt`, `forecasting/requirements.txt`, `capacity/requirements.txt`; run `make test`, then `pytest service/tests -q`; ruff as a non-blocking step.
2. `.github/pull_request_template.md`: module, what changed, contract impact (yes/no), how tested.
3. Root `README.md`: what the project is (3 lines), architecture diagram reference, module/owner table with **status** column, quick start (local), how to run each module, link to `contracts/README.md`, AWS hygiene rules. Fix the `:8080` vs `:8090` mismatch in the root `Makefile` comment via a tiny separate PR tagged for Member 1.
4. Create `docs/` with `docs/README.md` (index).

**Accept:** CI runs on a PR and goes green; a deliberately broken test makes it red (then revert).

### W2 — Service core, offline (target: 10 Nov)
1. Build `oracle_service/` per §6: config, schemas, engine, sources (`sample` + `local`), store (`LocalStore`), pipeline, alerts (logic only, sending stubbed when `ALERT_TOPIC_ARN` empty), api.
2. Turn `service/api/app.py` into the shim; existing `service/tests/test_api.py` must pass unchanged.
3. Fix the `history()` cutoff bug; `history` returns newest first.
4. Add `GET /metrics/recent`.
5. `service/scripts/pull_local_metrics.sh` (uses `docker compose -f workload/docker-compose.yml cp app1:/data/metrics.csv ...` for app1..3).
6. `service/Makefile`: `run-api` (uvicorn on :8000), `pipeline-once`, `test`.
7. Tests: engine (sample rows → valid C2/C3; whatif 500 and 5000 both valid; input C2 not mutated), store, sources (local), pipeline (end to end into a temp dir), alerts (null exhaustion → no alert; within window → alert; duplicate suppressed).

**Accept:** with Docker stack running and `make load PATTERN=spike`, then `pull_local_metrics.sh` and `ORACLE_SOURCE=local make -C service pipeline-once`, `/plan/latest` returns a C3 built from those metrics; all tests green.

### W3 — Dashboard (target: 13 Nov)
`service/dashboard/app.py`, single page, sidebar with API URL (default from `ORACLE_API_URL` / `st.secrets`), "offline mode" toggle (imports `oracle_service` directly), refresh button, `st.cache_data(ttl=60)` on GETs.

Panels, top to bottom:
1. **Status strip:** recommendation (big), reason, forecast model + MAPE, `generated_at` age ("updated 7 min ago"), source badge (sample/live).
2. **Exhaustion countdown:** "CPU reaches 70% in 3 h 12 min (18:45 UTC)" or "No exhaustion in the next 24 h" when null; amber under 6 h, red under 1 h.
3. **Forecast vs actual:** Plotly line chart, x = time; actual `requests_per_min` from `/metrics/recent` (solid), forecast (dashed) with `lower`/`upper` band shaded; second chart for `cpu_pct` with a horizontal 70% threshold line.
4. **Options:** two cards side by side (scale-out / scale-up): instances × type, $/hour, $/day, expected latency, single point of failure yes/no; highlight the recommended one. Below: bandwidth Mbps, storage GB in 30 days, current setup and its $/hour.
5. **What-if:** number input (default 5000 req/min) + button → `POST /plan` → render the same two cards for the result, plus a one-line delta vs current.
6. **History:** `/history?days=7` → line of recommended $/day over time and a small table (time, peak rpm, recommendation).

Handle: API unreachable (show message + "switch to offline mode"), empty history, `null` fields, slow responses (spinners). Screenshot each panel into `docs/img/` for the report.

**Accept:** `streamlit run service/dashboard/app.py` works in offline mode and against `make -C service run-api`.

### W4 — AWS deploy (target: 18 Nov)
Before starting: run `aws sts get-caller-identity --profile oracle-m4` and do a dry permission check (§9). If AccessDenied on IAM/ECR/Lambda, stop and list exactly which permissions to ask Member 1 for.

`service/deploy/up.sh` (idempotent: describe-then-create-or-update), in this order:
1. **ECR** repo `oracle-service` (scan on push, lifecycle policy: keep last 1 image).
2. **Build & push** `Dockerfile.lambda` (`--platform linux/arm64`, native on the Apple Silicon dev Mac, with Lambda `--architectures arm64`; `--provenance=false` so Lambda accepts the manifest; `pip --only-binary=:all:` because the AL2 base image has no compiler). Image copies `service/oracle_service`, `forecasting/`, `capacity/`, `contracts/`.
3. **DynamoDB** table `oracle-results` (PAY_PER_REQUEST, PK `kind`, SK `generated_at`, TTL on `ttl`).
4. **SNS** topic `oracle-alerts`; subscribe emails from `ALERT_EMAILS` env (each person must click the confirmation email).
5. **IAM role** `oracle-lambda-role`: `AWSLambdaBasicExecutionRole` + inline least-privilege policy: `s3:ListBucket`/`s3:GetObject` on the metrics bucket, `dynamodb:PutItem/Query/GetItem` on `oracle-results`, `sns:Publish` on `oracle-alerts`.
6. **Lambda** `oracle-api` (image, architecture **arm64**, `CMD` → `oracle_service.lambda_handlers.api_handler`, 1024 MB, 30 s timeout) and `oracle-pipeline` (same image, image-config command override → `pipeline_handler`, 1024 MB, 120 s timeout). Env vars from §6 with `ORACLE_STORE=dynamo`, `ORACLE_SOURCE=s3`. Reserved concurrency 2 each (caps runaway cost) — **not possible on account 149236595048** (concurrency limit 10, AWS keeps 10 unreserved); up.sh warns and API throttling is the guard until the limit is raised.
7. **CloudWatch Logs** retention 7 days on both log groups.
8. **API Gateway HTTP API** `oracle-api` with a `$default` route → `oracle-api` Lambda (`aws apigatewayv2 create-api --protocol-type HTTP --target <arn>`), `lambda add-permission` for apigateway, stage throttling **rate 5 rps, burst 10**. Print the URL.
9. **EventBridge Scheduler** schedule `oracle-pipeline-15min` (`rate(15 minutes)`) with role `oracle-scheduler-role` allowed `lambda:InvokeFunction` on `oracle-pipeline`. Create it **DISABLED** by default; `make -C service schedule-on` / `schedule-off` toggle it. Turn it on only during integration windows and the final demo week.
10. Tag everything `project=oracle`.

`down.sh`: delete in reverse order. `--keep-data` flag keeps the DynamoDB table and SNS topic. Always deletes the schedule first.

`smoke.sh`: hits all endpoints, checks status codes and JSON keys, runs `POST /plan` with 500 and 5000.

**Accept:** `make -C service deploy` from clean → `smoke.sh` passes; invoking `oracle-pipeline` manually writes a new plan visible in `/history`; forcing an alert (test event `{"force_alert": true}` handled in `pipeline_handler`) delivers one email; `make -C service down` leaves nothing tagged `project=oracle` from Module 4 (verify with `aws resourcegroupstaggingapi get-resources --tag-filters Key=project,Values=oracle`).

### W5 — Public dashboard (target: 20 Nov)
1. Deploy `service/dashboard/app.py` on Streamlit Community Cloud from the public repo, branch `main`, requirements from `service/dashboard/requirements.txt`.
2. Set `ORACLE_API_URL` in Streamlit secrets (it's a public URL, not a credential, but keep it out of code anyway).
3. Put the dashboard URL in root README and in SNS email bodies.

**Accept:** dashboard loads from a phone on mobile data and shows live data.

### W6 — Integration routine (22 Nov – 5 Dec, every Tue and Sat)
`service/scripts/integrate.sh`:
1. `git pull` on `main`, `make test`.
2. Offline run: sample source → pipeline-once → validate C2/C3.
3. Local run: Docker stack + `make load PATTERN=spike RUN_S=300` → pull metrics → pipeline-once.
4. If AWS session is open: `smoke.sh`, invoke pipeline, check `/history` grew.
5. Write `docs/integration/<date>.md`: what passed, what broke, which module/owner, one line each. Human posts the summary in the group.

### W7 — Demo and report material (target: 8 Dec)
1. `docs/module4.md`: architecture of the service layer (diagram), API table, data store design, schedule/alert logic, deployment steps, cost analysis (estimated monthly usage vs free allowances, measured from CloudWatch for one week), screenshots, limitations.
2. A 3–4 minute screen recording of the end-to-end demo (Locust spike → pipeline → dashboard updates → what-if 500→5000 → alert email) as a backup if the network fails during evaluation.
3. Final checklist run: everything in §1 "Done means".

---

## 9. AWS details

**Credentials (human does this, not you):** `aws configure --profile oracle-m4` with Member 4's IAM keys, region `ap-south-1`, output `json`. Scripts use `AWS_PROFILE=oracle-m4`. Never read or echo the credentials file.

**Permissions Module 4 needs** (check before W4; if missing, ask Member 1 to attach):
ECR (create/push/lifecycle), Lambda (create/update/invoke/add-permission/concurrency), IAM (`CreateRole`, `PutRolePolicy`, `AttachRolePolicy`, `PassRole` limited to `oracle-*` roles), DynamoDB (create/describe/delete table, TTL), SNS (topic + subscribe), API Gateway v2, EventBridge Scheduler, CloudWatch Logs (retention), Resource Groups Tagging (read), S3 read on the metrics bucket.

**Resource names (single source: `service/deploy/config.sh`):**

| Resource | Name |
|---|---|
| ECR repo | `oracle-service` |
| Lambda (API) | `oracle-api` |
| Lambda (pipeline) | `oracle-pipeline` |
| API Gateway HTTP API | `oracle-api` |
| DynamoDB table | `oracle-results` |
| SNS topic | `oracle-alerts` |
| Schedule | `oracle-pipeline-15min` |
| IAM roles | `oracle-lambda-role`, `oracle-scheduler-role` |
| Log groups | `/aws/lambda/oracle-api`, `/aws/lambda/oracle-pipeline` |

**Cost guards (all mandatory):** schedule disabled except during integration/demo; reserved concurrency 2; API throttling 5 rps / burst 10; 7-day log retention; ECR keeps 1 image (500 MB free storage); DynamoDB TTL 30 days; on-demand billing only. Expected usage (96 pipeline runs/day × ~10 s × 1 GB ≈ 29k GB-s/month) is far below Lambda's free allowance — record the real numbers in `docs/module4.md`.

**Kept between sessions:** Lambda functions, API Gateway, DynamoDB, SNS, ECR (all idle-free). **Never left on:** the schedule (unless in an agreed window).

---

## 10. Testing strategy

- Unit tests per file in `service/tests/`, runnable with pytest; `test_api.py` must also run as a plain script (used by `make test`).
- AWS code tested with `moto` (`@mock_aws`), never real AWS. Set fake credentials in a fixture (`AWS_ACCESS_KEY_ID=testing`, etc.).
- Contract tests: every C2/C3 produced by the pipeline validates against `schemas.py`, and the sample files validate too (catches drift in either direction).
- Golden what-if test: `whatif(500)` and `whatif(5000)` both return two options; instances for 5000 ≥ instances for 500.
- Dashboard: a smoke test that imports `service/dashboard/app.py` functions (keep rendering logic in pure functions where possible).
- Before every PR: `make test && pytest service/tests -q`.

---

## 11. Coding conventions

- Type hints on public functions; docstrings one line + contract reference where relevant.
- No `print` in library code — use `logging` with JSON-ish one-line messages (`{"event": "pipeline_done", "ms": 812, ...}`).
- Times: always timezone-aware UTC; serialize with trailing `Z` (match the contracts).
- No boto3 calls outside `sources.py`, `store.py`, `alerts.py`. Create clients lazily so imports work offline.
- Small PRs (< ~400 lines), one work package each, title `M4: <what>`.

---

## 12. Open questions — ask the team, don't guess

Record each in `PROGRESS.md` "Needs team decision" until answered:

1. **Aggregation across instances (Members 2 & 3).** C1 has one row per instance per minute. Should `forecast()` receive raw rows or app-level totals (sum `requests_per_min`, mean `cpu_pct`/`mem_pct` per minute)? Should `baseline()` get per-instance rows? Default until answered: `forecast` gets per-minute totals (`AGGREGATE_MODE=per_minute_total`), `baseline` gets raw rows.
2. **Metrics bucket name and retention (Member 1).** Value for `METRICS_BUCKET`; confirm keys stay `metrics/{instance}/metrics-*.csv` and each upload is cumulative.
3. **Forecast runtime (Member 2).** Will the Lambda need statsmodels/Prophet/TensorFlow at inference? Sets image size and memory.
4. **Pricing data (Member 3).** Confirm `capacity/pricing.json` ships inside the package and `plan()` needs no network calls.
5. **Who receives alert emails** (list of addresses for `ALERT_EMAILS`).
6. **IAM permissions** for the Member 4 user (see §9) — Member 1 is the account admin.

---

## 13. Session protocol (every session)

**Start:** read `service/PROGRESS.md`, then this file's relevant section, then `git pull`. **End:** update `PROGRESS.md`, commit, push your branch.

`service/PROGRESS.md` template:

```
# Module 4 progress
Last updated: <date> by <agent/human>

COMPLETED:
-
IN PROGRESS:
-
NEXT:
-
NEEDS TEAM DECISION:
- Q1 aggregation across instances — default per_minute_total (asked <date>)
KNOWN BUGS:
-
AWS STATE (what exists right now):
- nothing deployed
LESSONS (mistakes not to repeat):
-
```

When the human corrects you, add a line under LESSONS so the next session doesn't repeat it.

---

## 14. Troubleshooting notes

- **Docker needs sudo on Omarchy** until `omarchy setup security sudoless docker` + reboot (from Member 1).
- **Locust** is installed in `workload/.venv`; `make load PATTERN=spike RUN_S=300` stops after 300 s.
- **Lambda "image manifest not supported"** → rebuild with `--provenance=false` and `--platform linux/arm64` (must match the function's `arm64` architecture).
- **Lambda import errors** for `forecasting`/`capacity` → they must be copied to `${LAMBDA_TASK_ROOT}` and importable as top-level packages (both have `__init__.py`).
- **DynamoDB float errors** → you stored numbers instead of the JSON string `body`; store JSON text.
- **SNS emails not arriving** → subscription still "PendingConfirmation"; check the inbox/spam.
- **API Gateway 500 with no logs** → missing `lambda add-permission` for `apigateway.amazonaws.com`.
- **Streamlit Cloud build fails** → it must find `service/dashboard/requirements.txt` next to `app.py`; pin Python 3.11 in the app's advanced settings.
- **Budget alert email received** → run `make -C service down` and `make down`, then tell the human before doing anything else.
