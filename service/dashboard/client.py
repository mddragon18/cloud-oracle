"""API client for the dashboard, with an offline fallback that calls oracle_service directly."""
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

TS_KEYS = ("generated_at", "exhaustion_at", "timestamp")


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def shift_times(doc, delta: timedelta):
    """Copy of doc (dict/list, nested) with every generated_at / exhaustion_at / timestamp moved by delta. None stays None."""
    if isinstance(doc, list):
        return [shift_times(x, delta) for x in doc]
    if not isinstance(doc, dict):
        return doc
    return {k: (_iso(datetime.fromisoformat(v) + delta) if k in TS_KEYS and isinstance(v, str) else shift_times(v, delta))
            for k, v in doc.items()}


def demo_delta(sample_c2: dict, now: datetime) -> timedelta:
    """Offset that makes the sample's newest metric row (first forecast point minus one step) land on `now`."""
    newest = datetime.fromisoformat(sample_c2["series"][0]["timestamp"]) - timedelta(minutes=sample_c2["step_minutes"])
    return now.replace(second=0, microsecond=0) - newest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
TIMEOUT_S = 15


class ApiError(Exception):
    """API unreachable or returned an error; message is safe to show."""


class Client:
    def __init__(self, base_url: str | None, now: datetime | None = None):
        """base_url None -> offline mode (no HTTP). Offline sample data is shifted so it reads as current (demo only)."""
        self.base_url = (base_url or "").rstrip("/") or None
        self.now = now
        self._delta = None

    def _demo(self, doc, src: str = "sample"):
        """Demo/offline only: move contract-sample timestamps to now. Stored local results and live data are untouched."""
        if self.base_url or src != "sample":
            return doc
        if self._delta is None:
            from service.oracle_service import core
            sample_c2 = json.loads(core.SAMPLES["forecast"].read_text())
            self._delta = demo_delta(sample_c2, self.now or datetime.now(UTC))
        return shift_times(doc, self._delta)

    def _http(self, method: str, path: str, **kw) -> tuple[dict, str]:
        try:
            r = requests.request(method, self.base_url + path, timeout=TIMEOUT_S, **kw)
        except requests.RequestException as e:
            raise ApiError(f"API unreachable at {self.base_url} ({type(e).__name__})") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise ApiError(f"{path} returned {r.status_code}: {str(detail)[:200]}")
        return r.json(), r.headers

    def _offline(self, fn, *args):
        # Offline = contract sample data only: never S3/DynamoDB, never AWS credentials.
        os.environ["ORACLE_SOURCE"] = "sample"
        os.environ["ORACLE_STORE"] = "local"
        # core is FastAPI-free, so Streamlit Cloud needs no fastapi
        from service.oracle_service import core

        try:
            return fn(core)(*args)
        except Exception as e:
            raise ApiError(f"offline mode failed: {str(e)[:200]}") from e

    def forecast(self) -> tuple[dict, str, dict]:
        """-> (C2, 'live'|'sample', {"confidence": "low"|"normal", "data_age_minutes": int|None, "replay_at": str|None})."""
        if self.base_url:
            doc, h = self._http("GET", "/forecast/latest")
            age = h.get("X-Oracle-Data-Age-Minutes")
            return doc, h.get("X-Oracle-Source", "live"), {
                "confidence": h.get("X-Oracle-Confidence", "normal"), "data_age_minutes": int(age) if age else None,
                "replay_at": h.get("X-Oracle-Replay-At")}
        doc, src = self._offline(lambda a: a.latest, "forecast")
        doc = self._demo(doc, src)
        return doc, src, self._offline(lambda a: a.quality, doc, self.now)

    def plan(self) -> tuple[dict, str]:
        if self.base_url:
            doc, h = self._http("GET", "/plan/latest")
            return doc, h.get("X-Oracle-Source", "live")
        doc, src = self._offline(lambda a: a.latest, "plan")
        return self._demo(doc, src), src

    def whatif(self, rpm: int) -> dict:
        if self.base_url:
            return self._http("POST", "/plan", json={"expected_rpm": rpm})[0]
        return self._offline(lambda a: a.whatif_plan, rpm)

    def history(self, days: int = 7) -> list[dict]:
        if self.base_url:
            return self._http("GET", "/history", params={"days": days})[0]["plans"]
        return self._offline(lambda a: a.history, days)

    def recent(self, hours: int = 24) -> list[dict]:
        if self.base_url:
            return self._http("GET", "/metrics/recent", params={"hours": hours})[0]["rows"]
        return self._demo(self._offline(lambda a: a.recent_metrics, hours))  # offline source is always the sample
