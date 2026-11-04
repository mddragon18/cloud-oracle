"""Pydantic mirrors of C2/C3 (contracts/*.sample.json). Extra keys allowed on input."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")


class Accuracy(_M):
    mape_pct: float
    rmse: float


class SeriesPoint(_M):
    timestamp: str
    requests_per_min: float
    cpu_pct: float
    mem_pct: float
    lower: float
    upper: float


class C2(_M):
    generated_at: str
    model: str
    horizon_minutes: int
    step_minutes: int
    accuracy: Accuracy
    series: list[SeriesPoint] = Field(min_length=1)
    cpu_threshold_pct: float
    exhaustion_at: str | None


class Current(_M):
    instances: int
    instance_type: str
    usd_per_hour: float


class Option(_M):
    strategy: Literal["scale_out", "scale_up"]
    instances: int
    instance_type: str
    usd_per_hour: float
    usd_per_day: float
    expected_latency_ms: float
    single_point_of_failure: bool


class C3(_M):
    generated_at: str
    peak_requests_per_min: float
    current: Current
    options: list[Option] = Field(min_length=2, max_length=2)
    bandwidth_mbps: float
    storage_gb_30d: float
    recommendation: Literal["scale_out", "scale_up"]
    reason: str
    exhaustion_at: str | None


class WhatIf(BaseModel):
    expected_rpm: int = Field(ge=1, le=1_000_000)


class ContractError(Exception):
    """Another module produced a C2/C3 that breaks the contract."""


def validate(kind: str, doc: dict) -> dict:
    """Validate a C2 ('forecast') or C3 ('plan'); returns doc unchanged or raises ContractError."""
    try:
        {"forecast": C2, "plan": C3}[kind].model_validate(doc)
    except ValidationError as e:
        raise ContractError(f"{kind} breaks contract: {e.errors()[:3]}") from e
    return doc
