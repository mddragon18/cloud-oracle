# Module 4 progress
Last updated: 2026-11-04 by Claude (agent)

COMPLETED:
- W4 deployed 2026-11-04 (draft PR #9 -> ready); W5 prep PR #10 merged; dashboard memory % chart (85% line) next to CPU
- W0: Python 3.11 venv (uv), `make test` green; HANDOFF.md in service/ (branch m4-setup)
- W1: CI workflow (installs service + forecasting + capacity reqs, `make test`, pytest, ruff non-blocking), PR template, root README, docs/ index (m4-ci)
- W2: oracle_service package (sample/local/S3 sources, Local/Dynamo stores, pipeline, alerts, API + /metrics/recent), shim, tests (m4-service-core)
- Team decisions 2026-11-04: AGGREGATE_MODE default "raw" (aggregate() kept for /metrics/recent); C2 accuracy fields nullable, model free str; skipped test documents Member 3 storage bug
- W2 finish: stale-metrics warning (data_age_minutes in run summary, >30 min warns), ruff clean, /metrics/recent in contracts/README API table
- Makefile :8080 -> :8090 comment fix on branch m4-makefile-port (for Member 1)
- W3: Streamlit dashboard (service/dashboard/) with all 6 panels, offline toggle, error states; pure helpers + AppTest render smoke test (m4-dashboard)
- W3 checked against `make -C service run-api` (2026-11-04): live badge, all panels, what-if POST /plan 5000 -> 6 x t3.micro, API-down message; fixed $ prices rendering as LaTeX
- GitHub: PRs #2 m4-setup, #3 m4-ci (CI green), #4 m4-service-core, #6 m4-dashboard (stacked, each builds on the previous), #5 m4-makefile-port (review: mddragon18); issue #7 for Member 1 (collector + locustfile)
IN PROGRESS:
- W2 Docker acceptance: BLOCKED on Member 1 bugs (see KNOWN BUGS). ORACLE_SOURCE=local path verified with synthetic 3-instance CSVs (180 rows -> live C3 via /plan/latest)
NEXT:
- Get #2 -> #3 -> #4 -> #6 reviewed and merged in order
- Re-run Docker acceptance after Member 1 fixes issue #7
- W3: dashboard screenshots into docs/img/ once real data flows
- W5: Streamlit Cloud app + ORACLE_API_URL secret; schedule-on only in integration/demo windows
NEEDS TEAM DECISION:
- Q2 METRICS_BUCKET name + confirm cumulative uploads (Member 1)
- Q3 forecast runtime deps in Lambda (Member 2) — ARIMA needs statsmodels; check image size
- Q4 pricing.json packaged, no network in plan() (Member 3)
- Q5 ALERT_EMAILS list
- Q6 resolved 2026-11-04: OracleM4Deploy policy attached (no iam:ListRoleTags; get-role shows tags)
- Post in group: additive endpoint GET /metrics/recent?hours=24
- Root .gitignore: added data/forecast/, data/plan/, data/alert/, data/local-metrics/ — shared file, flag in PR
KNOWN BUGS (other modules — not fixed here):
- Real S3 run 2026-11-04 14:36Z: only 20 rows in S3 (collector uploads stopped ~13:37) -> forecast() picks naive model, whose linear
  trend runs away over 24 h: peak 84,728 rpm, CPU 100%, memory -> 0%; plan 35 x t3.micro $9.41/day. Member 1's local ARIMA on the
  full CSV: ~5,616 rpm, 2 x t3.micro $0.54/day. Needs: more S3 history (Member 1) and a bounded naive fallback (Member 2).
- data/aws-run-2026-11-04.csv is NOT in the repo: root .gitignore `*.csv` drops it (only contracts/*.csv, data/*.sample.csv allowed).
- Member 3: baseline() storage_gb_per_day wrong with >1 instance (divides by row count, diffs disk across different instances; 2 instances growing 1 GB/day report 12.49). Test: service/tests/test_integration_capacity.py (skipped, "owned by Member 3")
- Member 1 (issue #7, fixes merged 2026-11-04): workload/app/collector.py uses net.bytes_in/bytes_out; psutil has bytes_recv/bytes_sent -> collector thread dies on its first row, metrics.csv stays header-only
- Member 1: workload/locust/locustfile.py fails on locust 2.31: imports Shape (-> LoadTestShape), WorkloadUser(User) has no HTTP client (-> HttpUser), shape() generator (-> tick() returning (users, spawn))
- Member 1: root Makefile `load` has no RUN_S (hard-coded -t 2m), handoff assumes RUN_S
- Member 1: psutil 5.9 has no linux/arm64 wheel; on Apple Silicon build with DOCKER_DEFAULT_PLATFORM=linux/amd64 (and pull nginx:alpine for amd64)
- Main still has stub forecast(); with raw rows it does not sum across instances (peak 429 for 3x~170 rpm). Expected to change with Member 2's merge.
AWS STATE (account 149236595048, ap-south-1) — 2026-11-04 after full deploy:
- API URL: https://fsenmc8m46.execute-api.ap-south-1.amazonaws.com  (Streamlit secret ORACLE_API_URL)
- ECR oracle-service (lifecycle keeps 1; 2 images until expiry runs), DynamoDB oracle-results (3 plans + forecasts + 2 alert docs),
  SNS oracle-alerts (theomeshsengar@gmail.com confirmed), IAM oracle-lambda-role + oracle-scheduler-role,
  Lambda oracle-api + oracle-pipeline (arm64, 1024 MB), log groups /aws/lambda/oracle-* (7 d), HTTP API oracle-api (5 rps/burst 10)
- Schedule oracle-pipeline-15min: DISABLED (no tags possible; down.sh deletes it by name)
- No reserved concurrency (account limit 10); API throttling is the guard
- Verified: smoke.sh 7/7 PASS; pipeline {"source":"sample"} ok; real S3 run ok; /history 3 plans; forced alert sent
LESSONS (mistakes not to repeat):
- zsh: "$VAR:u" is an uppercase modifier; brace ${VAR} before a colon.
- Lambda base image (AL2, glibc 2.26) has no compiler: pip --only-binary=:all:.
- Streamlit markdown treats $..$ as LaTeX: escape dollar signs as \\$.
- GitHub returned intermittent 5xx on push/PR create (2026-11-04): retry, then check for duplicates.
- Member 1 = mddragon18 (repo admin, wrote Module 1 scaffold) — inferred, confirm with team.
- Paths may contain spaces: quote "$(ROOT)" in Makefiles.
- Streamlit: don't touch st.secrets without a secrets.toml (renders an error box); embedded browser may hang on localhost websockets, use 127.0.0.1.
NOTES:
- Extra dev deps: httpx (FastAPI TestClient); dashboard requirements pulled into requirements-dev for the AppTest smoke test.
- Lookback window is measured from the newest metric row; pipeline warns when that row is >30 min old.
