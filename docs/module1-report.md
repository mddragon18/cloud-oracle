# Module 1 — Workload & Metrics Collection (Member 1)

Report section for the Phase III write-up. Everything here is reproducible from
this repo; the raw evidence lives in `data/` and S3 `s3://cloud-oracle-metrics-149236595048/metrics/`.

## What Module 1 produces
- **App + collector** (`workload/app.py`): tiny Flask app (`/`, `/compute`, `/download`)
  with an in-container metrics collector that writes one C1 row per minute and
  uploads the cumulative CSV to S3 every 5 min when `S3_BUCKET` is set.
- **Load generator** (`workload/locust/locustfile.py`): four shapes — `steady`,
  `cycle`, `spike`, `growth` — selectable via `PATTERN`; `RUN_S` stop-guard so
  headless runs end cleanly.
- **Topology**: 3 app replicas behind nginx (`workload/docker-compose.yml` for
  laptop demo at `:8090`; `infra/aws-up.sh` reproduces it on one EC2 box with
  plain `docker run` because AL2023 ships no compose).
- **Contract**: writes **C1 `metrics.csv`** — `timestamp,instance_id,instance_type,
  requests_per_min,avg_latency_ms,p95_latency_ms,cpu_pct,mem_pct,net_in_kb,
  net_out_kb,disk_used_gb,workload_pattern` — frozen schema, headers unchanged
  since Oct 28.

## Real AWS runs (t3.micro, ap-south-1, free plan)

| Run | Window (UTC) | Rows | Load | Outcome |
|---|---|---|---|---|
| Nov-4 rehearsal | 13:10–13:37 | 20 | steady 620 rpm cluster | OOM at ~620 rpm (RAM binds, not CPU); credits exhausted ~5 min; spike pattern = 502s |
| Nov-5 dense steady | 07:43–09:03 | 243 | steady ~330 rpm, 57 min | 18,720 requests, **0 failures**; baseline-capped all hour |
| Nov-5 pattern sweep | 10:14–11:19 | 198 | cycle 36–94, growth 12–112, spike peak 182 rpm/replica | all shapes visible in C1, **0 failures incl. at spike peak** — see `data/aws-run-2026-11-05-patterns-notes.md` |

Datasets + per-run notes in `data/aws-run-2026-11-05*.csv|md`, `data/aws-run-2026-11-04*.csv|md`.

## Key findings (measure-driven, corrected the plan's assumptions)
1. **Locust scales at ~55 rpm/user against this box**, not the docstring's
   "250 users ≈ 500 rpm" (~4× optimistic). `PEAK_USERS=6` is the ~330 rpm steady
   sweet spot; 120 users peg CPU at 99%.
2. **Burst credits drain in ~5 min of high load** and *unlimited mode is blocked
   on free-plan accounts*. Keep steady CPU under the ~12% t3.micro baseline and
   the box runs indefinitely at baseline — no throttling symptoms at 330 rpm.
3. **RAM, not CPU, is the binding limit** on t3.micro: 3 replicas OOM at ~620 rpm;
   at ~110 rpm/replica `mem_pct` still peaks ~95% host-wide — thin but survivable.
4. `cpu_pct_per_100rpm` measures **2.7 pre-cap** and **~7.9 while baseline-capped**
   — M2's "500 rpm ↔ 35% CPU" assumption was ~2.5× pessimistic, but the capped
   number must not be extrapolated to uncapped loads.
5. SG exposes only `:8090` → no SSH; monitoring stack for the runs is
   CloudWatch `CPUUtilization`/`CPUCreditBalance` + locust's own stats.

## Cost hygiene (Phase III requirement: bill stays zero)
- t3.micro + S3 + IAM: all inside free-tier/credits; `infra/aws-down.sh` verified
  to leave zero running instances and deletes the SG after a 20 s grace.
- Standing resources between sessions: bucket, `oracle-budget` ($1 alarm →
  SNS `oracle-budget-alerts`, email confirmed), IAM users m2/m3/m4 scoped keys,
  key pair. Budget alarm test-published and delivered.

## Repro recipe
```bash
infra/aws-up.sh                      # box + docker build (~4 min), prints DNS
PATTERN=steady PEAK_USERS=6 RUN_S=3600 workload/.venv/bin/locust \
  -f workload/locust/locustfile.py -H http://<DNS>:8090 --headless   # safe load
aws s3 ls s3://cloud-oracle-metrics-149236595048/metrics/ --recursive
infra/aws-down.sh                    # teardown after every session
```
