# AWS run — 2026-11-05 pattern sweep (cycle / growth / spike)

Same box recipe as the morning dense run (t3.micro, 3 replicas, `infra/aws-up.sh`),
load all in the safe envelope (`BASE_USERS=2`, `PEAK_USERS=6`; spike phase 10).
Window 10:14–11:19 UTC. **198 C1 rows** in `aws-run-2026-11-05-patterns.csv`.

| Phase (UTC) | Shape | Rows | rpm per replica | Locust | Outcome |
|---|---|---|---|---|---|
| 10:14–10:42 | `cycle` (sine, CYCLE_S=900, 2 cycles) | 84 | 36–94 (avg 65) | 5,582 req | 0 failures; sine fully visible in `requests_per_min` |
| 10:43–11:01 | `growth` (+2 users/30s → 6) | 54 | 12–112 (avg 101) | 5,851 req | 0 failures; ramp from 12 → ~110 rpm visible |
| 11:02–11:15 | `spike` (2→10 users, 60–180s of 300s, ×2) | 39 | 35–182 (avg 96) | 4,013 req | **0 failures at spike peak ~550 rpm cluster** (p95 430 ms, p100 1.5 s) — Nov-4's 502 storm is gone at this size |
| 11:16–11:19 | idle tail | 12 | 0 | — | post-load baseline rows |

Notes for consumers (M2/M3):
- The `workload_pattern` column carries the container's static env (`steady`) —
  the *locust* pattern is only inferable from timestamps; use the table above.
- Box ran baseline-capped (credits 0 from earlier runs; unlimited blocked on free
  plan), so rpm values are the sustainable ceiling, not full-uncapped throughput.
- Cumulative snapshots mirrored in S3 `metrics/i-0*-app/metrics-20261105T1119*Z.csv`.
- Load generator caveat: the `cycle` phase was cut by a harness time-limit at
  28 of 30 min (2 sine cycles survived); growth/spike ran full.
