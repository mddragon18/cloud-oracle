# Module 4 progress
Last updated: 2026-11-04 by Claude (agent)

COMPLETED:
- W0: Python 3.11 venv (uv), `make test` green; HANDOFF.md in service/ (branch m4-setup)
- W1: CI workflow (installs service + forecasting + capacity reqs, `make test`, pytest, ruff non-blocking), PR template, root README, docs/ index (m4-ci)
- W2: oracle_service package (sample/local/S3 sources, Local/Dynamo stores, pipeline, alerts, API + /metrics/recent), shim, tests (m4-service-core)
- Team decisions 2026-11-04: AGGREGATE_MODE default "raw" (aggregate() kept for /metrics/recent); C2 accuracy fields nullable, model free str; skipped test documents Member 3 storage bug
- W2 finish: stale-metrics warning (data_age_minutes in run summary, >30 min warns), ruff clean, /metrics/recent in contracts/README API table
- Makefile :8080 -> :8090 comment fix on branch m4-makefile-port (for Member 1)
- W3: Streamlit dashboard (service/dashboard/) with all 6 panels, offline toggle, error states; pure helpers + AppTest render smoke test (m4-dashboard)
IN PROGRESS:
- W2 Docker acceptance: BLOCKED on Member 1 bugs (see KNOWN BUGS). ORACLE_SOURCE=local path verified with synthetic 3-instance CSVs (180 rows -> live C3 via /plan/latest)
NEXT:
- Push branches / open PRs once the collaborator invite is accepted
- Re-run Docker acceptance after Member 1 fixes collector + locustfile
- W3: dashboard screenshots into docs/img/ once real data flows; check against `make -C service run-api`
- W4 only after the human confirms METRICS_BUCKET and IAM permissions
NEEDS TEAM DECISION:
- Q2 METRICS_BUCKET name + confirm cumulative uploads (Member 1)
- Q3 forecast runtime deps in Lambda (Member 2) — ARIMA needs statsmodels; check image size
- Q4 pricing.json packaged, no network in plan() (Member 3)
- Q5 ALERT_EMAILS list
- Q6 IAM permissions for Member 4 user (Member 1)
- Post in group: additive endpoint GET /metrics/recent?hours=24
- Root .gitignore: added data/forecast/, data/plan/, data/alert/, data/local-metrics/ — shared file, flag in PR
KNOWN BUGS (other modules — not fixed here):
- Member 3: baseline() storage_gb_per_day wrong with >1 instance (divides by row count, diffs disk across different instances; 2 instances growing 1 GB/day report 12.49). Test: service/tests/test_integration_capacity.py (skipped, "owned by Member 3")
- Member 1: workload/app/collector.py uses net.bytes_in/bytes_out; psutil has bytes_recv/bytes_sent -> collector thread dies on its first row, metrics.csv stays header-only
- Member 1: workload/locust/locustfile.py fails on locust 2.31: imports Shape (-> LoadTestShape), WorkloadUser(User) has no HTTP client (-> HttpUser), shape() generator (-> tick() returning (users, spawn))
- Member 1: root Makefile `load` has no RUN_S (hard-coded -t 2m), handoff assumes RUN_S
- Member 1: psutil 5.9 has no linux/arm64 wheel; on Apple Silicon build with DOCKER_DEFAULT_PLATFORM=linux/amd64 (and pull nginx:alpine for amd64)
- Main still has stub forecast(); with raw rows it does not sum across instances (peak 429 for 3x~170 rpm). Expected to change with Member 2's merge.
AWS STATE (what exists right now):
- nothing deployed
LESSONS (mistakes not to repeat):
- Paths may contain spaces: quote "$(ROOT)" in Makefiles.
- Streamlit: don't touch st.secrets without a secrets.toml (renders an error box); embedded browser may hang on localhost websockets, use 127.0.0.1.
NOTES:
- Extra dev deps: httpx (FastAPI TestClient); dashboard requirements pulled into requirements-dev for the AppTest smoke test.
- Lookback window is measured from the newest metric row; pipeline warns when that row is >30 min old.
