"""Small HTTP client for the Haunted Audit API (scripted mode only)."""
from __future__ import annotations

import requests

try:
    from night_watch.models import RunSnapshot
except ImportError:  # running from inside the night_watch folder
    from models import RunSnapshot


class ApiUnreachable(Exception):
    """Connection refused, DNS failure, or no answer within the timeout."""


class ApiBadResponse(Exception):
    """HTTP error (not 429), bad JSON, or a missing field."""


class RateLimited(Exception):
    """HTTP 429. retry_after is the raw Retry-After header text, or None."""

    def __init__(self, retry_after: str | None = None):
        super().__init__("rate limited")
        self.retry_after = retry_after


class ApiClient:
    def __init__(self, base_url: str, session=None, timeout: float = 10.0):
        self.base_url = base_url
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    def _send(self, method: str, path: str, **kwargs):
        """Send one request; turn connection problems into ApiUnreachable."""
        try:
            return self.session.request(
                method, self.base_url + path, timeout=self.timeout, **kwargs
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise ApiUnreachable(type(exc).__name__) from exc

    @staticmethod
    def _json_object(response) -> dict:
        """Parse the body as a JSON object or raise ApiBadResponse."""
        try:
            data = response.json()
        except ValueError as exc:
            raise ApiBadResponse("response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise ApiBadResponse("response JSON was not an object")
        return data

    def start_run(self, variant: str) -> str:
        """POST /runs and return the run_id."""
        body = {"variant": variant, "mode": "scripted"}
        response = self._send("POST", "/runs", json=body)
        if response.status_code == 429:
            raise RateLimited(response.headers.get("Retry-After"))
        if response.status_code != 202:
            raise ApiBadResponse(f"unexpected HTTP status {response.status_code}")
        data = self._json_object(response)
        run_id = data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ApiBadResponse("response had no run_id")
        return run_id

    def get_run(self, run_id: str) -> RunSnapshot:
        """GET /runs/{run_id} and return the values as received."""
        response = self._send("GET", "/runs/" + run_id)
        if response.status_code >= 400:
            raise ApiBadResponse(f"unexpected HTTP status {response.status_code}")
        data = self._json_object(response)
        for field in ("status", "verdict", "reason_code"):
            if field not in data:
                raise ApiBadResponse(f"response had no {field}")
        return RunSnapshot(data["status"], data["verdict"], data["reason_code"])
