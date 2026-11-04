# AWS run 2026-11-04 — measured numbers (account 149236595048, ap-south-1)

One t3.micro (2 vCPU / 1 GB), 3 app containers + nginx behind port 8090,
locust from laptop. Raw rows: `aws-run-2026-11-04.csv` (deduped from S3
`metrics/` uploads); also in S3 per-instance.

## Measured anchors (for M2 synthetic / M3 capacity model)

- **cpu_pct is host-wide psutil** on the shared box (nginx + 3 containers),
  13:23–13:37 single-instance phase: **~2,100 rpm @ ~57% CPU**, avg ~3.1 s,
  p95 ~5.5 s → `cpu_pct_per_100rpm ≈ 2.7` at cluster level.
- M2's synthetic assumes 500 rpm ≈ 35% CPU; measured extrapolation says
  500 rpm ≈ 13–14% CPU. Their assumption is ~2.5× pessimistic for this
  workload (light JSON + 1.5M-step compute + 4 MB download endpoints).
- **The binding constraint is RAM, not CPU**: host mem hit 99.5%, apps 2/3
  were OOM-killed within ~5 min of load at ~620 cluster rpm; nginx then
  served everything from the one survivor (C1 rows show `inst` count drop).
- **Burst credits**: t3.micro `CPUCreditBalance` hit 0 in ~5 min at our
  load; unlimited mode is **blocked on free-plan accounts** (AWS refuses to
  enable it). Sustained capacity without credits ≈ baseline only.
- **Spike (10×) at throttled/OOM'd state: 100% HTTP 502** (4,750 reqs, zero
  success). Steady phase overall: 65,203 reqs, 45% failed, avg 4.7 s.

## Demo conclusions (all defensible in Phase II)

1. t3.micro cannot host the 3-replica stack: **scale_up (t3.small/medium)
   beats scale_out** at this workload — matches M3's engine when RAM-aware.
2. Latency collapse under spike is real (502s), good p95/latency story.
3. `workload_pattern` column reads `steady` throughout (env-set, not
   measured) — documented caveat; spike evidence is in locust stats.
4. For a healthy run next time: fewer replicas (1–2), lower target rpm
   (~300), or a non-burstable/free instance.
