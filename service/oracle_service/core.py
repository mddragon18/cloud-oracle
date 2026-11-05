"""Plain dict-returning service functions (no FastAPI) — used by the API routes and the dashboard's offline mode."""
import json
from datetime import UTC, datetime, timedelta

from . import config, engine
from .alerts import STALE_MIN, low_confidence
from .config import REPO
from .schemas import validate
from .sources import get_source, parse_ts
from .store import get_store, iso

SAMPLES = {"forecast": REPO / "contracts" / "C2-forecast.sample.json",
           "plan": REPO / "contracts" / "C3-plan.sample.json"}


def latest(kind: str) -> tuple[dict, str]:
    """Latest stored C2/C3, else the contract sample. Returns (doc, 'live'|'sample')."""
    doc = get_store(config.load()).latest(kind)
    if doc is None:
        return json.loads(SAMPLES[kind].read_text()), "sample"
    return validate(kind, doc), "live"


def quality(c2: dict, now: datetime | None = None) -> dict:
    """Confidence for a C2 (not part of the contract; served as headers). Low = naive model, null accuracy,
    or newest metric row older than 30 min. The newest row is series[0] minus one step (forecast starts one step later).
    REPLAY_MODE measures from that row instead of the clock; replay_at is that row, None when replay is off."""
    now, replay = now or datetime.now(UTC), config.load().replay_mode
    age, replay_at = None, None
    try:
        last_row = parse_ts(c2["series"][0]["timestamp"]) - timedelta(minutes=c2["step_minutes"])
        if replay:
            now, replay_at = last_row, iso(last_row)
        age = max(0, round((now - last_row).total_seconds() / 60))
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    low = low_confidence(c2) or age is None or age > STALE_MIN
    return {"confidence": "low" if low else "normal", "data_age_minutes": age, "replay_at": replay_at}


def latest_forecast() -> dict:
    return latest("forecast")[0]


def latest_plan() -> dict:
    return latest("plan")[0]


def whatif_plan(expected_rpm: int) -> dict:
    """Fresh C3 for a what-if load, baseline from the current source. Not stored."""
    cfg = config.load()
    return engine.whatif(expected_rpm, get_source(cfg).get_rows(cfg.lookback_hours), cfg.aggregate_mode)


def history(days: float = 7) -> list[dict]:
    """Stored C3s within `days`, newest first."""
    return get_store(config.load()).since("plan", days)


def recent_metrics(hours: float = 24) -> list[dict]:
    """C1 rows aggregated per minute over the last `hours` of data."""
    cfg = config.load()
    return engine.aggregate(get_source(cfg).get_rows(hours), "per_minute_total")


def health() -> dict:
    return {"status": "ok"}
