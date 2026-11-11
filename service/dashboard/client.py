"""API client for the dashboard, with an offline fallback that calls oracle_service directly."""
import json
import os
import shutil
import sys
import tempfile
import threading
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TIMEOUT_S = 15
HEALTH_TIMEOUT_S = 3
RECORDED = sorted((REPO / "data").glob("aws-run-*.csv"))  # Member 1's recorded AWS runs, committed to the repo
EMBEDDED_BADGE = "Cloud backend offline: running the same code on recorded AWS data"
_ENV_KEYS = ("ORACLE_SOURCE", "ORACLE_STORE", "LOCAL_METRICS_DIR", "DATA_DIR", "REPLAY_MODE", "ALERT_TOPIC_ARN")
_ORIGINAL_ENV = {k: os.environ.get(k) for k in _ENV_KEYS}
_SAMPLE_ENV = {"ORACLE_SOURCE": "sample", "ORACLE_STORE": "local"}
_embedded_env: dict | None = None
_embedded_lock = threading.Lock()


def api_alive(url: str | None) -> bool:
    """True only if /health answers 200 with exactly {"status": "ok"} within HEALTH_TIMEOUT_S; anything else is down."""
    if not url:
        return False
    try:
        r = requests.get(url.rstrip("/") + "/health", timeout=HEALTH_TIMEOUT_S, allow_redirects=False)
        return r.status_code == 200 and r.json() == {"status": "ok"}
    except (requests.RequestException, ValueError):  # ValueError: body is not JSON
        return False


def _set_env(env: dict) -> None:
    # shortcut: os.environ is process-wide, so concurrent viewers in different offline modes could race; fine while
    # everyone on Cloud gets the same mode, revisit if sample and embedded viewers must coexist
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def embedded_env() -> dict:
    """Run the real pipeline once, in-process, on the recorded AWS CSVs into a temp local store (replay on, no SNS).
    Returns the env that reads that store. Nothing here touches AWS."""
    global _embedded_env
    with _embedded_lock:
        if _embedded_env is None:
            tmp = Path(tempfile.mkdtemp(prefix="oracle-embedded-"))
            (tmp / "metrics").mkdir()
            for f in RECORDED:
                shutil.copy(f, tmp / "metrics")
            env = {"ORACLE_SOURCE": "local", "ORACLE_STORE": "local", "LOCAL_METRICS_DIR": str(tmp / "metrics"),
                   "DATA_DIR": str(tmp), "REPLAY_MODE": "1", "ALERT_TOPIC_ARN": ""}
            _set_env(env)
            from service.oracle_service import pipeline
            pipeline.run_once()
            _embedded_env = env
        return _embedded_env


class ApiError(Exception):
    """API unreachable or returned an error; message is safe to show."""


class Client:
    def __init__(self, base_url: str | None, now: datetime | None = None, embedded: bool = False):
        """base_url None -> offline mode (no HTTP). Offline sample data is shifted so it reads as current (demo only).
        embedded=True (offline only) -> the recorded AWS run, processed in-process by embedded_env()."""
        self.base_url = (base_url or "").rstrip("/") or None
        self.embedded = embedded and not self.base_url
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
        # Offline never reaches S3/DynamoDB or AWS credentials: contract sample, or the recorded CSVs in the repo.
        if self.embedded:
            _set_env(embedded_env())
        else:
            if _embedded_env and os.environ.get("DATA_DIR") == _embedded_env["DATA_DIR"]:
                _set_env(_ORIGINAL_ENV)  # undo embedded mode's env, keep anything set outside it
            _set_env(_SAMPLE_ENV)
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
        src = "embedded" if self.embedded else src
        doc = self._demo(doc, src)
        return doc, src, self._offline(lambda a: a.quality, doc, self.now)

    def plan(self) -> tuple[dict, str]:
        if self.base_url:
            doc, h = self._http("GET", "/plan/latest")
            return doc, h.get("X-Oracle-Source", "live")
        doc, src = self._offline(lambda a: a.latest, "plan")
        src = "embedded" if self.embedded else src
        return self._demo(doc, src), src

    def whatif(self, rpm: int) -> dict:
        if self.base_url:
            return self._http("POST", "/plan", json={"expected_rpm": rpm})[0]
        return self._offline(lambda a: a.whatif_plan, rpm)

    def history(self, days: int = 7) -> list[dict]:
        if self.base_url:
            return self._http("GET", "/history", params={"days": days})[0]["plans"]
        return self._offline(lambda a: a.history, days)

    def accuracy(self, days: int = 7) -> dict:
        """-> {"window_hours": int, "rows": [{generated_at, model, error_pct_1h, error_pct_6h, error_pct_24h}]}."""
        if self.base_url:
            return self._http("GET", "/forecast-accuracy", params={"days": days})[0]
        return self._offline(lambda a: a.forecast_accuracy, days)

    def recent(self, hours: int = 24) -> list[dict]:
        if self.base_url:
            return self._http("GET", "/metrics/recent", params={"hours": hours})[0]["rows"]
        rows = self._offline(lambda a: a.recent_metrics, hours)
        return rows if self.embedded else self._demo(rows)  # sample rows are shifted to now; recorded rows stay real
