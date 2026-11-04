"""Plain dict-returning service functions (no FastAPI) — used by the API routes and the dashboard's offline mode."""
import json

from . import config, engine
from .config import REPO
from .schemas import validate
from .sources import get_source
from .store import get_store

SAMPLES = {"forecast": REPO / "contracts" / "C2-forecast.sample.json",
           "plan": REPO / "contracts" / "C3-plan.sample.json"}


def latest(kind: str) -> tuple[dict, str]:
    """Latest stored C2/C3, else the contract sample. Returns (doc, 'live'|'sample')."""
    doc = get_store(config.load()).latest(kind)
    if doc is None:
        return json.loads(SAMPLES[kind].read_text()), "sample"
    return validate(kind, doc), "live"


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
