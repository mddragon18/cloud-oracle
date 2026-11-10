# Module 4 progress
Last updated: 2026-11-04 (redeploy) by Claude (agent)

COMPLETED:
- m4-alert-guards: alerts skip stale (>30 min) and low-confidence forecasts (unless forced), 0..window only, one de-duped "capacity already exceeded" alert when fresh; X-Oracle-Confidence / X-Oracle-Data-Age-Minutes headers; dashboard amber banner + data age. Deployed 2026-11-04 14:53Z (image 4cb2c83, main after #9 + #11)
- W4 deployed 2026-11-04 (draft PR #9 -> ready); W5 prep PR #10 merged; dashboard memory % chart (85% line) next to CPU
- W0: Python 3.11 venv (uv), `make test` green; HANDOFF.md in service/ (branch m4-setup)
- W1: CI workflow (installs service + forecasting + capacity reqs, `make test`, pytest, ruff non-blocking), PR template, root README, docs/ index (m4-ci)
- W2: oracle_service package (sample/local/S3 sources, Local/Dynamo stores, pipeline, alerts, API + /metrics/recent), shim, tests (m4-service-core)
- Decision 2026-11-05: EXCLUDE_WINDOWS drops Nov-5 07:43-07:53Z tuning rows from every source (end exclusive). data/aws-run-2026-11-05-notes.md still says these rows were kept; Member 1 asked on 2026-11-05 to drop them, so that request wins until the notes are updated. Dashboard: https://cloud-oracle-ge5svfjhkafdnfipesqylt.streamlit.app
- Team decisions 2026-11-04: AGGREGATE_MODE default "raw" (aggregate() kept for /metrics/recent); C2 accuracy fields nullable, model free str; Member 3 storage bug fixed (storage_growth_gb_per_day), test un-skipped
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
- Member 3 — memory sizing (#17): 620 rpm per t3.micro is where the stack ran out of memory, not a safe limit, and Member 1 measured it as cluster rpm with 3 replicas on one t3.micro. Plan still recommends t3.micro scale-out.
- Member 1 (issue #7, fixes merged 2026-11-04): workload/app/collector.py uses net.bytes_in/bytes_out; psutil has bytes_recv/bytes_sent -> collector thread dies on its first row, metrics.csv stays header-only
- Member 1: workload/locust/locustfile.py fails on locust 2.31: imports Shape (-> LoadTestShape), WorkloadUser(User) has no HTTP client (-> HttpUser), shape() generator (-> tick() returning (users, spawn))
- Member 1: root Makefile `load` has no RUN_S (hard-coded -t 2m), handoff assumes RUN_S
- Member 1: psutil 5.9 has no linux/arm64 wheel; on Apple Silicon build with DOCKER_DEFAULT_PLATFORM=linux/amd64 (and pull nginx:alpine for amd64)
- Main still has stub forecast(); with raw rows it does not sum across instances (peak 429 for 3x~170 rpm). Expected to change with Member 2's merge.
AWS STATE (account 149236595048, ap-south-1) — deployed 2026-11-04, suspended ~2026-11-08, recovered and redeployed 2026-11-10:
- REPLAY_MODE (default off, also off on Lambda): age, confidence, alert window and countdown use the newest metric row; dashboard shows a replay badge. Turn on: REPLAY_MODE=1 make -C service deploy.
- Redeployed 2026-11-05 14:2xZ from main 6712062, then replay-on: REPLAY_MODE=1 on both Lambdas; smoke.sh 7/7 PASS; pipeline 431 rows, peak 268 rpm, data age 0, confidence low; schedule DISABLED.
- Account suspended for verification ~2026-11-08 to 2026-11-10: API down (404, then HTTP 500 on /health). Dashboard fell back to embedded mode (#26, #28). Nothing deployed meanwhile.
- Recovered 2026-11-10: new oracle-m4 key, account 149236595048 confirmed. Old Lambda smoke 5/7: POST /plan timed out because the bucket grew to 536 objects (~2,600 rows); fixed by parallel S3 reads (#29).
- Redeployed 2026-11-10 16:0xZ from main 95409f8 (REPLAY_MODE=1 kept): smoke.sh 7/7 PASS; pipeline 2,584 rows, 22.6 s, data through 2026-11-07T23:30Z. Model now arima (history > 2 days), MAPE 284%, confidence header "normal". Peak 379 rpm, recommended 2 x t3.micro $0.54/day, plan exhaustion_at 2026-11-24T11:25:50Z (forecast's own exhaustion_at is null). What-if 500 -> 2 x t3.micro $0.54; 5,000 -> 6 x t4g.small $2.42 (vs 10 x t3.micro $2.69), each ~19.5 s. SNS email subscription still confirmed; schedule DISABLED.
- Redeployed 2026-11-10 16:17Z from main 07581f8 (#31: MAPE > 25% is low confidence; pipeline stores kind=baseline; POST /plan uses stored forecast + baseline). REPLAY_MODE=1 on both. Pipeline then timed out twice at 120 s after the S3 read (locally the same run takes ~10 s): multi-threaded BLAS on Lambda's CPU share. Set OPENBLAS/OMP/MKL_NUM_THREADS=1 on both Lambdas (now in up.sh): pipeline 7.2 s, first baseline stored 16:25:31Z. smoke.sh 7/7 PASS. POST /plan 500 and 5,000 rpm: 0.13 to 0.17 s (was ~19.5 s). Confidence header low (ARIMA MAPE 284%). Schedule DISABLED.
- Redeployed 2026-11-10 17:21Z from main a1e1d69 (#33 Member 2 latest-stretch fit, model arima-short; #32 one-thread BLAS in up.sh). REPLAY_MODE=1 and OPENBLAS/OMP/MKL_NUM_THREADS=1 on both Lambdas after deploy. Pipeline 6.7 s (10 s wall), 2,584 rows. Forecast arima-short, MAPE 6.38% over the last 3 h (holdout_minutes 180), confidence normal, peak 342 rpm, exhaustion_at null in both C2 and C3 (the earlier out-of-window 2026-11-24 date is gone). Plan 2 x t3.micro $0.54/day. smoke.sh 7/7 PASS. POST /plan 500 -> 2 x t3.micro $0.54 (0.19 s); 5,000 -> 6 x t4g.small $2.42 vs 10 x t3.micro $2.69 (0.16 s). Schedule DISABLED.
- Deploy keeps the Lambda's REPLAY_MODE unless passed explicitly. Dashboard breaks actual lines at gaps over 5 min.
- Module 4 in maintenance mode from 2026-11-05: changes only on request.
- Replay switch: make -C service replay-on|replay-off (Lambda env only, keeps other vars, reruns pipeline). down.sh supports DRY_RUN=1. Demo script: service/DEMO.md.
- Dashboard accuracy panel reads forecasting/results/accuracy.md; LSTM column stays empty until #18 merges.
- make -C service deploy now runs test-all first (activate .venv); deploy scripts use set -euo pipefail, except sourced config.sh.
- Stray 84,728 rpm plans deleted from DynamoDB 2026-11-05.
- API URL: https://fsenmc8m46.execute-api.ap-south-1.amazonaws.com  (Streamlit secret ORACLE_API_URL)
- ECR oracle-service (lifecycle keeps 1; 2 images until expiry runs), DynamoDB oracle-results (3 plans + forecasts + 2 alert docs),
  SNS oracle-alerts (theomeshsengar@gmail.com confirmed), IAM oracle-lambda-role + oracle-scheduler-role,
  Lambda oracle-api + oracle-pipeline (arm64, 1024 MB), log groups /aws/lambda/oracle-* (7 d), HTTP API oracle-api (5 rps/burst 10)
- Schedule oracle-pipeline-15min: DISABLED (no tags possible; down.sh deletes it by name)
- No reserved concurrency (account limit 10); API throttling is the guard
- Verified: smoke.sh 7/7 PASS; pipeline {"source":"sample"} ok; real S3 run ok; /history 3 plans; forced alert sent
- Redeployed 2026-11-04 14:53Z from main 4cb2c83: smoke.sh 7/7 PASS; /plan/latest + /forecast/latest send X-Oracle-Confidence: low and X-Oracle-Data-Age-Minutes: 78 (stored forecast is naive, newest S3 row ~13:37Z); schedule DISABLED
- Redeployed 2026-11-05 07:32Z from 67a88f5 (main with #12, #15-#17): smoke.sh 7/7 PASS; real S3 run (20 rows): model naive, peak 1,837 rpm (was 84,728), exhaustion none, plan 3 x t3.micro $0.81/day limited by memory, confidence low, data age 1076 min; schedule DISABLED
- Redeployed 2026-11-05 11:29Z from cf6699f (S3Source reads all objects, deduped): smoke.sh 7/7 PASS; real S3 run: 461 rows (Nov-4 + Nov-5 steady + Nov-5 sweep; collection final, no 2-day run), model naive, peak 268 rpm, plan 2 x t3.micro $0.54/day, confidence low, data age 11 min; schedule DISABLED
LESSONS (mistakes not to repeat):
- zsh: "$VAR:u" is an uppercase modifier; brace ${VAR} before a colon.
- Lambda base image (AL2, glibc 2.26) has no compiler: pip --only-binary=:all:.
- Streamlit markdown treats $..$ as LaTeX: escape dollar signs as \\$.
- GitHub returned intermittent 5xx on push/PR create (2026-11-04): retry, then check for duplicates.
- Member 1 = mddragon18 (repo admin, wrote Module 1 scaffold) — inferred, confirm with team.
- Paths may contain spaces: quote "$(ROOT)" in Makefiles.
- AWS CLI: use ~/.local/bin/aws (2.39.3) with AWS_PROFILE=oracle-m4. The Homebrew aws broke on a libexpat mismatch (2026-11-05) and was uninstalled.
- Streamlit: don't touch st.secrets without a secrets.toml (renders an error box); embedded browser may hang on localhost websockets, use 127.0.0.1.
NOTES:
- Extra dev deps: httpx (FastAPI TestClient); dashboard requirements pulled into requirements-dev for the AppTest smoke test.
- Lookback window is measured from the newest metric row; pipeline warns when that row is >30 min old.
