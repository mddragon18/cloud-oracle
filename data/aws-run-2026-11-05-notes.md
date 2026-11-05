# AWS run — 2026-11-05 (dense steady dataset)

Instance: `i-03198d1019308e37c` (t3.micro, ap-south-1) · stack: 3 app replicas behind
nginx :8090 (plain `docker run` topology from `infra/aws-up.sh`) · load: locust
`PATTERN=steady` from laptop · window: 07:43–08:53 UTC (~70 min incl. tuning).

## Result: healthy dense run
- **243 C1 rows** in `aws-run-2026-11-05.csv` (81 per replica, 1 row/min, through
  09:03Z — the last 18 min are post-load idle rows at rpm 0).
- Steady phase (07:53–08:46Z, 159 rows): **~109 rpm/replica (~330 rpm cluster)**,
  0 failures over 18,720 requests, median 27 ms, p99 ~440 ms.
- Raw cumulative snapshots are in S3 `metrics/i-0*-app/metrics-20261105T*.csv`
  (one upload per 5 min; newest per instance = whole run).

## Load tuning (worth knowing before re-running)
- Locust scales at **~55 rpm per user** against this box, not the "250 users ≈ 500 rpm"
  in the locustfile docstring. 120 users = ~2,500 rpm → box pegged (CPU 99%, avg
  latency 2 s); 12 users still ~2,000 rpm; **6 users = the target ~330 rpm.**
- Burst credits: the hot bursts drained `CPUCreditBalance` to **0 in ~5 min** (confirms
  Nov-4 finding); unlimited mode is blocked on this free-plan account, so the box ran
  baseline-capped the rest of the hour — `cpu_pct` plateaus at ~10–12% with zero
  throttling symptoms at 300 rpm. Lesson: start low (`PEAK_USERS=6`), don't chase 500 rpm.

## For M2/M3
- Steady rows give `cpu_pct_per_100rpm ≈ 8` **while baseline-capped** (Nov-4's 2.7 was
  measured pre-cap) — the relationship is throttled, don't extrapolate it to 500 rpm.
- The 30 early "hot" rows (90–787 rpm, cpu up to 98.9%, mem 95%) are load-tuning
  artifacts, kept deliberately for the cpu↔rpm regression spread; for regression use
  the load window 07:53–08:46Z; forecast training can keep the idle tail too.
- `mem_pct` peaked at 95.5% host-wide at ~100 rpm/replica with 3 replicas — still no
  OOM, so RAM headroom at this load is thin but survivable. No spike/cycle/growth
  pattern rows in this run (steady only).
