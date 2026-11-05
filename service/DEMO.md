# Demo script

Dashboard: https://cloud-oracle-ge5svfjhkafdnfipesqylt.streamlit.app
API: https://fsenmc8m46.execute-api.ap-south-1.amazonaws.com

Setup for every terminal step: `source .venv/bin/activate`, `export AWS_PROFILE=oracle-m4`, run from the repo root.

## Before you present
1. Check the mode. With replay on, the dashboard shows the "Replay of recorded run (2026-11-05)" badge.
2. `make -C service smoke`: expect 7 PASS lines.
3. Keep the dashboard open. Streamlit Cloud sleeps when idle, so load it a few minutes early.

`make -C service deploy` resets replay to off. Run `make -C service replay-on` after any deploy.

## Click-by-click

### 1. Dashboard tour (2 min)
Figures below are from the replay run with 431 rows; check them on the day.
1. Open the dashboard. Point at the badge: this is a recorded run, measured from its newest row.
2. Read the amber banner: low confidence, because recorded data is too short for ARIMA.
3. Read the headline: **Scale out to 2 × t3.micro**, $0.54/day against $16.32/day to scale up.
4. Show the runway: no exhaustion in the next 24 h.
5. Walk the KPI row: peak 268 req/min, recommended $0.54/day, current $0.81/day, bandwidth 21.0 Mbps, storage 2.2 GB.
6. Scroll to **Forecast vs actual**. Black is recorded data, dashed blue is the forecast. The long diagonal lines join separate runs and are not real traffic.
7. Show the CPU chart with its 70% limit and the memory chart with its 85% limit.

### 2. Accuracy panel (1 min)
1. Scroll to **Model accuracy (offline evaluation)**.
2. Say the caption: live runs are ~1 h, so 24 h accuracy is measured on Wikipedia and Azure traces.
3. Compare Wikipedia: ARIMA 3.28% against same-time-yesterday 4.68%.
4. Be upfront about Azure: same-time-yesterday (0.85%) beats ARIMA (1.32%).
5. LSTM values appear only after PR #18 merges.

### 3. What-if, 500 → 5,000 rpm (2 min)
1. Scroll to **What-if**.
2. Enter `500`, click **Plan for this load**. Expect 2 × t3.micro at $0.54/day.
3. Enter `5000`, click **Plan for this load**. Expect 9 × t3.micro at $2.42/day, marked **limited by memory**.
4. Compare scale-up, which stays at 2 × c6i.2xlarge at $16.32/day.
5. If asked: the 620 rpm memory limit per t3.micro is where the stack ran out of memory, so it has no safety margin.

### 4. History (30 s)
1. Scroll to **History (7 days)**.
2. Show how recommended cost changed as more real data arrived.

### 5. Forced alert email (1 min)
This sends a real email to every confirmed subscriber.
1. Run:
   ```bash
   EVENT='{"force_alert": true}' make -C service invoke
   ```
2. Open the inbox and show the "[oracle] test alert" email, its options and the dashboard link.

## Demo day: live mode
Live mode only looks current if new metrics are being uploaded. Data collection is final, so without a new run the data stays stale and confidence stays low. In that case stay on replay.

```bash
make -C service replay-off
```

```bash
make -C service schedule-on
```

```bash
make -C service smoke
```

Afterwards:

```bash
make -C service schedule-off
```

## Docker fallback
For when AWS or Streamlit Cloud is unavailable. This path has not been re-run end to end since Member 1's fixes.

```bash
make up
```

```bash
PATTERN=spike make load
```

```bash
service/scripts/pull_local_metrics.sh
```

```bash
ORACLE_SOURCE=local make -C service pipeline-once PY=python
```

Start each of these in its own terminal, with the same variable:

```bash
ORACLE_SOURCE=local make -C service run-api PY=python
```

```bash
ORACLE_API_URL=http://127.0.0.1:8000 make -C service run-dash PY=python
```

Open http://127.0.0.1:8501, then stop the stack with `make down`.

If Docker fails too, run `make -C service run-dash PY=python` alone: Offline mode uses the contract sample and needs no AWS.
