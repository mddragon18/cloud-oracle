# Cloud Cost & Capacity Oracle — "Predict Before You Scale"

Watches a cloud app's metrics, forecasts the next 24 h of load, and recommends how much
infrastructure is needed, when, and at what cost (scale-out vs scale-up) before capacity
runs out. Runs entirely on the AWS Free plan — the bill must stay at zero.

Architecture: workload → C1 metrics (S3) → `forecast()` → C2 → `plan()` → C3 → service
(API + schedule + alerts) → dashboard. Diagram and full plan: `Cloud Cost & Capacity Oracle — Team Work Plan.pdf`.
Frozen formats: [`contracts/README.md`](contracts/README.md).

## Modules

| Folder | Module | Owner | Status |
|---|---|---|---|
| `contracts/` | C1–C3 samples + schema notes | Member 4 (everyone reviews) | frozen |
| `workload/`, `infra/` | 1 — app, collector, Locust, AWS experiment infra | Member 1 | done (3 real AWS runs + datasets; report: `docs/module1-report.md`) |
| `forecasting/` | 2 — `load_metrics()`, `forecast()` | Member 2 | stub (linear trend) |
| `capacity/` | 3 — `baseline()`, `plan()`, `pricing.json` | Member 3 | stub (placeholder prices) |
| `service/` | 4 — API, pipeline, dashboard, deploy | Member 4 | offline core done; dashboard + AWS next |

## Quick start (local, no AWS)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r service/requirements.txt -r service/requirements-dev.txt -r forecasting/requirements.txt
make test                          # every module against the contract samples
make -C service pipeline-once      # forecast + plan from sample metrics into data/
make -C service run-api            # API on http://localhost:8000/docs
```

Per module:

```bash
make up && make load PATTERN=spike # Module 1: app x3 behind nginx at :8090, Locust load
python forecasting/forecast.py     # Module 2: writes data/forecast.out.json
python capacity/plan.py            # Module 3: writes data/plan.out.json
make down
```

Module 4 details: [`service/README.md`](service/README.md).

## Rules

- **Contracts are frozen.** Changing a C1–C3 format needs team agreement.
- **Own your folder.** Touch another module only through a PR its owner approves.
- **Branches:** `m1-*` … `m4-*` → PR into `main`; CI runs `make test` + `pytest service/tests`; `main` stays green.
- **Python 3.11**, each module keeps its own `requirements.txt`.
- **Secrets:** AWS keys only in local `.env` / AWS CLI profiles / GitHub Actions secrets — never in the repo.
- **AWS hygiene:** region `ap-south-1` only, tag everything `project=oracle`, tear down after every
  session (`make down`, `make -C service down`). Docker Compose is the complete offline fallback demo.
