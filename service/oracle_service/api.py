"""FastAPI app: contract endpoints + additive GET /metrics/recent. Routes never touch boto3."""
import json
import logging

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core import (  # noqa: F401  (re-exported for service/api/app.py and tests)
    SAMPLES,
    health,
    history,
    latest,
    latest_forecast,
    latest_plan,
    quality,
    recent_metrics,
    whatif_plan,
)
from .schemas import ContractError, WhatIf

log = logging.getLogger(__name__)


app = FastAPI(title="oracle-service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   expose_headers=["X-Oracle-Source", "X-Oracle-Confidence", "X-Oracle-Data-Age-Minutes", "X-Oracle-Replay-At"])


@app.exception_handler(ContractError)
def _contract_error(_, exc: ContractError):
    log.error(json.dumps({"event": "contract_error", "error": str(exc)[:300]}))
    return JSONResponse(status_code=502, content={"detail": "upstream module broke the contract"})


@app.exception_handler(ValueError)
def _no_data(_, exc: ValueError):
    return JSONResponse(status_code=503, content={"detail": str(exc)[:200]})


def _headers(response: Response, src: str, c2: dict) -> None:
    """Metadata outside C2/C3: X-Oracle-Source, X-Oracle-Confidence (low|normal), X-Oracle-Data-Age-Minutes."""
    q = quality(c2)
    response.headers["X-Oracle-Source"] = src
    response.headers["X-Oracle-Confidence"] = q["confidence"]
    if q["data_age_minutes"] is not None:
        response.headers["X-Oracle-Data-Age-Minutes"] = str(q["data_age_minutes"])
    if q["replay_at"]:
        response.headers["X-Oracle-Replay-At"] = q["replay_at"]


@app.get("/forecast/latest")
def api_forecast(response: Response):
    doc, src = latest("forecast")
    _headers(response, src, doc)
    return doc


@app.get("/plan/latest")
def api_plan(response: Response):
    doc, src = latest("plan")
    _headers(response, src, latest("forecast")[0])  # a plan is as trustworthy as the forecast behind it
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
