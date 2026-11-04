import copy
import json

from service.oracle_service import engine
from service.oracle_service.config import REPO
from service.oracle_service.schemas import validate
from service.oracle_service.sources import SampleSource


def rows():
    return SampleSource().get_rows(168)


def test_samples_validate():
    validate("forecast", json.loads((REPO / "contracts/C2-forecast.sample.json").read_text()))
    validate("plan", json.loads((REPO / "contracts/C3-plan.sample.json").read_text()))


def test_forecast_and_plan_valid_and_c2_not_mutated():
    c2 = engine.run_forecast(engine.aggregate(rows()))
    before = copy.deepcopy(c2)
    c3 = engine.run_plan(c2, engine.run_baseline(rows()))
    assert c2 == before and len(c3["options"]) == 2


def test_whatif_golden():
    lo, hi = engine.whatif(500, rows()), engine.whatif(5000, rows())
    assert len(lo["options"]) == len(hi["options"]) == 2
    out = lambda p: next(o for o in p["options"] if o["strategy"] == "scale_out")["instances"]
    assert out(hi) >= out(lo) and hi["peak_requests_per_min"] == 5000


def test_aggregate_sums_rpm_means_cpu():
    r = [{"timestamp": "t", "instance_id": i, "instance_type": "t3.micro", "workload_pattern": "steady",
          "requests_per_min": 100.0, "avg_latency_ms": 1.0, "p95_latency_ms": 2.0, "cpu_pct": c,
          "mem_pct": 50.0, "net_in_kb": 1.0, "net_out_kb": 1.0, "disk_used_gb": 1.0}
         for i, c in (("a", 20.0), ("b", 40.0))]
    (a,) = engine.aggregate(r)
    assert a["requests_per_min"] == 200 and a["cpu_pct"] == 30 and a["instances"] == 2


def test_null_accuracy_and_any_model_validate():
    c2 = json.loads((REPO / "contracts/C2-forecast.sample.json").read_text())
    c2["accuracy"] = {"mape_pct": None, "rmse": None}
    c2["model"] = "arima"
    validate("forecast", c2)


def test_default_mode_is_raw():
    from service.oracle_service import config
    assert config.load().aggregate_mode == "raw" and engine.aggregate(rows(), "raw") == rows()
