"""FastAPI app: contract endpoints + additive GET /metrics/recent. Routes never touch boto3."""
import json
import logging

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, engine
from .config import REPO
from .schemas import ContractError, WhatIf, validate
from .sources import get_source
from .store import get_store

log = logging.getLogger(__name__)
SAMPLES = {"forecast": REPO / "contracts" / "C2-forecast.sample.json",
           "plan": REPO / "contracts" / "C3-plan.sample.json"}


# Plain functions (dashboard offline mode + legacy shim call these without HTTP).
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


app = FastAPI(title="oracle-service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


@app.exception_handler(ContractError)
def _contract_error(_, exc: ContractError):
    log.error(json.dumps({"event": "contract_error", "error": str(exc)[:300]}))
    return JSONResponse(status_code=502, content={"detail": "upstream module broke the contract"})


@app.exception_handler(ValueError)
def _no_data(_, exc: ValueError):
    return JSONResponse(status_code=503, content={"detail": str(exc)[:200]})


@app.get("/forecast/latest")
def api_forecast(response: Response):
    doc, src = latest("forecast")
    response.headers["X-Oracle-Source"] = src
    return doc


@app.get("/plan/latest")
def api_plan(response: Response):
    doc, src = latest("plan")
    response.headers["X-Oracle-Source"] = src
    return doc


@app.post("/plan")
def api_post_plan(body: WhatIf):
    return whatif_plan(body.expected_rpm)


@app.get("/history")
def api_history(days: float = Query(7, gt=0, le=30)):
    return {"plans": history(days)}


@app.get("/metrics/recent")
def api_metrics(hours: float = Query(24, gt=0, le=168)):
    return {"rows": recent_metrics(hours)}


@app.get("/health")
def api_health():
    return health()
