# Module 4 progress
Last updated: 2026-11-04 by Claude (agent)

COMPLETED:
- W0: repo cloned, Python 3.11 venv (uv), `make test` green (3 OK lines); HANDOFF.md copied into service/
- W1: CI workflow, PR template, root README, docs/ index (branch m4-ci)
- W2: oracle_service package offline (sample/local sources, LocalStore + DynamoStore, pipeline, alerts, API + /metrics/recent), shim, tests (branch m4-service-core)
IN PROGRESS:
-
NEXT:
- Push branches + open PRs (needs push access to mddragon18/cloud-oracle)
- Separate tiny PR for Member 1: root Makefile comment says :8080, real port :8090
- W2 acceptance with Docker stack (`make up`, `make load PATTERN=spike`, pull_local_metrics.sh, pipeline-once) — not yet run
- W3 dashboard
NEEDS TEAM DECISION:
- Q1 aggregation across instances — default per_minute_total (asked 2026-11-04)
- Q2 METRICS_BUCKET name + confirm cumulative uploads (Member 1)
- Q3 forecast runtime deps in Lambda (Member 2)
- Q4 pricing.json packaged, no network in plan() (Member 3)
- Q5 ALERT_EMAILS list
- Q6 IAM permissions for Member 4 user (Member 1)
- Post in group: additive endpoint GET /metrics/recent?hours=24
- Root .gitignore: added data/forecast/, data/plan/, data/alert/ (LocalStore output) — shared file, flag in PR
KNOWN BUGS:
-
AWS STATE (what exists right now):
- nothing deployed
LESSONS (mistakes not to repeat):
-
NOTES:
- Extra dev dep `httpx` (not in §7): required by FastAPI's TestClient for API tests.
- Lookback window is measured from the newest metric row, not wall-clock now, so the old sample C1 still works offline.
