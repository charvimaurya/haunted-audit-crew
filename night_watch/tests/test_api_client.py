"""Tests for ApiClient using a stub session (no network)."""
import pytest
import requests
from hypothesis import given, settings, strategies as st

from night_watch.api_client import (
    ApiBadResponse, ApiClient, ApiUnreachable, RateLimited,
)


class StubResponse:
    def __init__(self, status=200, body=None, headers=None, bad_json=False):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("bad")
        return self._body


class StubSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


def client(**kw):
    session = StubSession(**kw)
    return ApiClient("http://127.0.0.1:8000", session=session), session


# Feature: night-watch, Property 3: Request bodies contain only variant and mode
@settings(max_examples=100)
@given(st.text())
def test_start_run_body_exact(variant):
    c, s = client(response=StubResponse(202, {"run_id": "run-1"}))
    assert c.start_run(variant) == "run-1"
    method, url, kw = s.calls[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8000/runs")
    assert kw["json"] == {"variant": variant, "mode": "scripted"}
    assert kw["timeout"] == 10.0


def test_429_keeps_raw_retry_after():
    c, _ = client(response=StubResponse(429, headers={"Retry-After": " 7x "}))
    with pytest.raises(RateLimited) as info:
        c.start_run("broken")
    assert info.value.retry_after == " 7x "


def test_429_without_header():
    c, _ = client(response=StubResponse(429))
    with pytest.raises(RateLimited) as info:
        c.start_run("broken")
    assert info.value.retry_after is None


@pytest.mark.parametrize("resp", [
    StubResponse(200, {"run_id": "r"}),
    StubResponse(500, {}),
    StubResponse(202, bad_json=True),
    StubResponse(202, {}),
    StubResponse(202, [1]),
])
def test_start_run_bad_responses(resp):
    c, _ = client(response=resp)
    with pytest.raises(ApiBadResponse):
        c.start_run("fixed")


@pytest.mark.parametrize("err", [
    requests.ConnectionError(), requests.Timeout(),
])
def test_unreachable(err):
    c, _ = client(error=err)
    with pytest.raises(ApiUnreachable):
        c.start_run("broken")
    with pytest.raises(ApiUnreachable):
        c.get_run("run-1")


def test_get_run_returns_values_as_received():
    body = {"status": "Complete", "verdict": 5, "reason_code": None}
    c, s = client(response=StubResponse(200, body))
    snap = c.get_run("run-1")
    assert (snap.status, snap.verdict, snap.reason_code) == ("Complete", 5, None)
    assert s.calls[0][:2] == ("GET", "http://127.0.0.1:8000/runs/run-1")


@pytest.mark.parametrize("resp", [
    StubResponse(404, {"detail": "run not found"}),
    StubResponse(200, bad_json=True),
    StubResponse(200, {"status": "running", "verdict": None}),
])
def test_get_run_bad_responses(resp):
    c, _ = client(response=resp)
    with pytest.raises(ApiBadResponse):
        c.get_run("run-1")
