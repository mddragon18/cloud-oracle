"""run_once(): source -> engine -> store -> alerts (HANDOFF §6)."""
import json
import logging
import time
from datetime import UTC, datetime

from . import alerts, config, engine
from .sources import get_source, parse_ts
from .store import get_store

log = logging.getLogger(__name__)
STALE_MIN = 30


def run_once(cfg: config.Config | None = None, force_alert: bool = False) -> dict:
    """One pipeline run. Stores nothing partial; re-raises so Lambda marks the run failed."""
    cfg = cfg or config.load()
    t0 = time.monotonic()
    try:
        rows = get_source(cfg).get_rows(cfg.lookback_hours)
        age = round((datetime.now(UTC) - parse_ts(rows[-1]["timestamp"])).total_seconds() / 60)
        if age > STALE_MIN:  # lookback is measured from the newest row, so stale data looks "current"
            log.warning(json.dumps({"event": "stale_metrics", "data_age_minutes": age}))
        c2 = engine.run_forecast(engine.aggregate(rows, cfg.aggregate_mode))
        c3 = engine.run_plan(c2, engine.run_baseline(rows))
        store = get_store(cfg)
        store.put("forecast", c2)
        store.put("plan", c3)
        alert = alerts.check(c3, store, cfg, force=force_alert)
    except Exception:
        log.exception(json.dumps({"event": "pipeline_failed", "ms": round((time.monotonic() - t0) * 1000)}))
        raise
    summary = {"event": "pipeline_done", "rows": len(rows), "generated_at": c3["generated_at"],
               "recommendation": c3["recommendation"], "exhaustion_at": c3["exhaustion_at"],
               "alert": alert, "data_age_minutes": age, "ms": round((time.monotonic() - t0) * 1000)}
    log.info(json.dumps(summary))
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(run_once(), indent=2))
