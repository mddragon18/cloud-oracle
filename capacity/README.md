# Capacity and Cost Engine (Member 3)

This package calculates infrastructure capacity, compares cloud scaling strategies, estimates costs, and recommends an appropriate configuration based on forecast demand.

Scope: Only the capacity and cost engine (Module 3). It operates independently using synthetic or real C1/C2 contracts and does not modify other members' directories.

## Installation

```bash
cd capacity
pip install -r requirements.txt
```

Requires Python 3.11+ (tested on 3.14) with `pandas`, `numpy`, and `pytest`.

## Public Interfaces

```python
from capacity import baseline, plan, plan_for_rpm

# Process historical metrics (C1)
baseline_result = baseline(metrics_df)

# Generate a C3 plan from a forecast (C2) and baseline result
plan_result = plan(forecast=forecast_dict, baseline=baseline_result)

# What-if: evaluate at a different traffic rate
plan_5000 = plan_for_rpm(forecast=forecast_dict, baseline_result=baseline_result, expected_rpm=5000.0)
```

### `baseline(metrics_df) -> dict`

Input: pandas DataFrame with C1 columns (`timestamp`, `instance_id`, `instance_type`, `requests_per_min`, `avg_latency_ms`, `p95_latency_ms`, `cpu_pct`, `mem_pct`, `net_in_kb`, `net_out_kb`, `disk_used_gb`, `workload_pattern`).

Output keys and units:
- `cpu_pct_per_100_rpm`: CPU % per 100 requests/min (median robust estimate; linear approximation).
- `kb_per_request`: Network traffic per request (`net_in_kb + net_out_kb`) / `requests_per_min`. Units: decimal KB/request (per-minute traffic, not cumulative counters).
- `storage_growth_gb_per_day`: Linear growth slope median across instances with sufficient history. `None` when history is insufficient.
- `current_disk_used_gb`: Latest median disk usage (GB).
- `latest_instance_type`: Most frequent instance type at the latest timestamp.
- `instance_count_latest`: Number of unique instances at latest timestamp.
- `avg_latency_ms`: Median observed average latency.
- `p95_latency_ms`: Median observed p95 latency.
- `per_instance_type_capacity`: Empty dict in Phase II (awaiting Member 1 measurements).

### `plan(forecast: dict, baseline: dict) -> dict`

Produces Contract C3 output with:
- `generated_at`: UTC ISO 8601 timestamp.
- `peak_requests_per_min`: Peak from forecast series (or override).
- `current`: Current instance count, type, and hourly cost.
- `options`: Scale-out and scale-up options with instances, instance type, hourly/daily cost, estimated latency, and SPOF boolean.
- `bandwidth_mbps`: Traffic at peak * kb/request converted to Mbps (`traffic_kb/min * 8 / (60 * 1000)`).
- `storage_gb_30d`: `current_disk_used_gb + storage_growth_gb_per_day * 30`.
- `recommendation`: `scale_out` or `scale_up`.
- `reason`: Numerical explanation including cost difference, savings percentage, latency comparison, and reliability note.
- `exhaustion_at`: Propagated from forecast (or `None`).

### `plan_for_rpm(...)`

Safe adapter for hypothetical loads. Validates `expected_rpm` is positive and finite, then calls `plan()` with an internal override.

## Formulas

- CPU cost coefficient: `cpu_pct * 100 / requests_per_min`
- Capacity per instance at target CPU: `target_cpu_pct * 100 / cpu_pct_per_100_rpm`
- Instance count: `ceil(peak_requests_per_min / capacity_per_instance_rpm) + 1`
- Bandwidth (Mbps): `traffic_kb_per_min * 8 / (60 * 1000)`
- 30-day storage: `current_disk + growth_gb_per_day * 30`
- Hourly cost: `instances * price_per_hour`
- Daily cost: `hourly * 24`

## Scale-Out vs Scale-Up Policy

1. Exclude infeasible options (negative capacity, missing prices, non-finite values).
2. Prefer `scale_out` when it is cheaper, avoids a single-point-of-failure, and its latency is within 10% of `scale_up`.
3. Otherwise choose the lowest-cost feasible option with acceptable latency.
4. If no feasible option exists, raise `ValueError` rather than recommending an unsupported plan.

Latency estimates are provisional (simplified Phase II estimator). They are not observed response times. Scale-up latency is assumed 10% lower than scale-out (faster instance) for demonstration; real measurements will replace this in Phase III.

Capacity multipliers for larger instance types (`PROVISIONAL_CAPACITY_MULTIPLIER`) are explicitly provisional and must be replaced with Member 1 measurements in Phase III.

## Pricing Cache and Retrieval

- Cache file: `capacity/pricing.json`
- Region: `ap-south-1` (Asia Pacific / Mumbai)
- Operating system: Linux; tenancy: Shared; purchase model: On-demand.
- The retrieval script (`scripts/fetch_prices.py`) uses `urllib` to query the AWS Price List API directly. It does not require boto3 or AWS credentials.
- The script validates all prices (finite, non-negative) and only overwrites the cache when results are complete.
- Unit tests (`tests/test_pricing.py`) verify loading, validation, and that network failures do not corrupt the existing cache.
- The current `pricing.json` contains test fixtures (not verified live prices). Always label synthetic data accordingly.

## Tests

```bash
pytest capacity/tests/
```

Tests cover:
- Baseline: valid input, division-by-zero protection, missing columns, NaN/inf handling, empty datasets, storage growth, network units.
- Sizing: capacity at 60/70/80%, instance count formula, integer/non-integer boundaries, invalid inputs.
- Pricing: valid cache load, missing prices, invalid prices, mocked API parsing, network failure isolation.
- Engine: C3 keys/types, both options, cost calculations, recommendation policy, exhaustion time propagation, what-if helper, JSON serialisability.

All tests work offline once `pricing.json` exists. No AWS credentials are required.

## Demonstration

```bash
python -m capacity.scripts.demo
```

Runs synthetic C1-shaped data (2 instances, 10 minutes), evaluates 500 and 5,000 requests/minute, prints baseline assumptions, capacity, costs, latency estimates, recommendations, and serialises the 5,000 RPM plan to `demo_plan_5000.json`.

Synthetic assumptions are labelled clearly in the output.

## Price Retrieval Command

```bash
python -m capacity.scripts.fetch_prices
```

This attempts a live retrieval; in environments without internet access it fails safely and does not corrupt the existing cache.

## Integration for Member 4

Import the package directly in Lambda/Service:

```python
from capacity import baseline, plan, plan_for_rpm
```

The engine has no external network dependencies (uses cached `pricing.json`) and no AWS credential requirements. It is safe to import and call synchronously.

## Phase III Readiness

- Extension point for M/M/c latency estimation and Little's Law concurrency checks is reserved in the design.
- Per-instance-type capacity measurements will replace `PROVISIONAL_CAPACITY_MULTIPLIER` once Member 1 provides measured results.
- Sensitivity analysis at 60%, 70%, and 80% CPU targets is supported via `target_cpu_pct`.
- Storage growth regression and network calculations are modular and can be enhanced with interval-delta logic when cumulative counters are confirmed.

## Assumptions and Limitations

- `net_in_kb` and `net_out_kb` are treated as per-minute traffic values, not cumulative counters. If they are cumulative, interval deltas must be computed first.
- Storage growth requires at least two observations per instance over a positive time span; otherwise `None` is returned.
- Latency estimates are provisional. Real latency measurements from Member 1 must replace the 10% scale-up assumption.
- Scale-up capacity relies on configured provisional multipliers. These are explicitly documented and clearly separated from measured observations.
- The price fixture (`pricing.json`) is a test-only cache. Production use requires running `fetch_prices.py` or confirming the fixture against live AWS rates.
- The demonstration produces simulated results, not verified cloud performance.
