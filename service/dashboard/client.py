"""API client for the dashboard, with an offline fallback that calls oracle_service directly."""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
TIMEOUT_S = 15


class ApiError(Exception):
    """API unreachable or returned an error; message is safe to show."""


class Client:
    def __init__(self, base_url: str | None):
        """base_url None -> offline mode (no HTTP)."""
        self.base_url = (base_url or "").rstrip("/") or None

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
        return r.json(), r.headers.get("X-Oracle-Source", "live")

    def _offline(self, fn, *args):
        from service.oracle_service import api
        try:
            return fn(api)(*args)
        except Exception as e:
            raise ApiError(f"offline mode failed: {str(e)[:200]}") from e

    def forecast(self) -> tuple[dict, str]:
        if self.base_url:
            return self._http("GET", "/forecast/latest")
        return self._offline(lambda a: a.latest, "forecast")

    def plan(self) -> tuple[dict, str]:
        if self.base_url:
            return self._http("GET", "/plan/latest")
        return self._offline(lambda a: a.latest, "plan")

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
        return self._offline(lambda a: a.recent_metrics, hours)
