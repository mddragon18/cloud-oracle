# Cloud Cost & Capacity Oracle

A team project that monitors a real workload, forecasts its next 24 h of load, and
recommend the cheapest scaling strategy (scale-out vs scale-up) before capacity
runs out. Runs entirely on the AWS Free plan — the bill must stay at zero.

See the work plan PDF (`Cloud Cost & Capacity Oracle — Team Work Plan.pdf`) for the
full plan. Quick rules:

- **Contracts are frozen.** `contracts/` holds C1–C3 sample files; changing a format
  needs team agreement.
- **Own your folder.** Only touch another module through a PR approved by its owner.
- **Branches:** `m1-*`, `m2-*`, `m3-*`, `m4-*` → PR into `main`; `main` must always pass tests.
- **Python 3.11**, each module keeps its own `requirements.txt`.
- **Secrets:** AWS keys only in local `.env` files and GitHub Actions secrets, never in the repo.
- **AWS hygiene:** one region (`ap-south-1`), tag everything `project=oracle`,
  `make down` after every session. Docker Compose is the complete offline fallback demo.

## Layout

| Folder | Module | Owner |
|---|---|---|
| `contracts/` | C1–C3 sample files + schema notes | Member 4 (everyone reviews) |
| `workload/` | 1 — FastAPI app + collector + Locust | Member 1 |
| `infra/` | 1 — AWS scripts (`make up` / `make down`) | Member 1 |
| `forecasting/` | 2 — loaders, models, `forecast()` | Member 2 |
| `capacity/` | 3 — `baseline()`, `plan()`, `pricing.json` | Member 3 |
| `service/` | 4 — FastAPI + Streamlit dashboard | Member 4 |
| `data/` | small samples only — real data stays in S3 | — |
| `docs/` | report, paper, diagrams | — |

## Local demo (no AWS needed)

```bash
make up      # Docker Compose: app x 3 behind nginx at http://localhost:8090
make load    # one Locust pattern (PATTERN=steady|cycle|spike|growth)
make down    # stop everything
make test    # run every module's tests against the contract samples
```
