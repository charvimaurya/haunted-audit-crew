"""Example tests for the Night Watch runner (fake API, fake clock, no network)."""
import json
from datetime import datetime, timezone

import pytest

from night_watch import run_journeys as rj
from night_watch.api_client import (
    ApiBadResponse, ApiClient, ApiUnreachable, RateLimited,
)
from night_watch.config import ConfigError, DEFAULT_API_URL, normalize_api_url
from night_watch.judge import judge
from night_watch.models import RunSnapshot
from night_watch.report import NO_AI_SENTENCE, build_report, write_report
from night_watch.retry import parse_retry_after
from night_watch.tests.fakes import FakeApi, FakeClock, complete, running

URL = "http://127.0.0.1:8000"
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
GOOD = {"broken": [complete("BLOCKED", "TARGET_NOT_FOCUSABLE")],
        "fixed": [complete("PASSED")]}


def go(tmp_path, starts=None, polls=None, clock=None):
    """Run the whole check with fakes. Returns (code, report, paths, api, clock)."""
    api = FakeApi(starts=starts, polls=polls or GOOD)
    clock = clock or FakeClock()
    code, report, paths = rj.run_check(api, clock, tmp_path / "reports", URL, lambda: WHEN)
    return code, report, paths, api, clock


def by_variant(report):
    return {v["variant"]: v for v in report["variants"]}


# ---- exit codes ----

def test_all_as_expected_exit_0(tmp_path):
    code, report, paths, _, _ = go(tmp_path)
    assert code == 0 and report["outcome"] == "all_as_expected"
    assert all(p.exists() for p in paths)


def test_fixed_blocked_is_returning_ghost_exit_1(tmp_path):
    polls = {"broken": GOOD["broken"], "fixed": [complete("BLOCKED", "FOCUS_TRAP")]}
    code, _, paths, _, _ = go(tmp_path, polls=polls)
    assert code == 1
    assert "returning ghost" in paths[0].read_text(encoding="utf-8")


def test_refused_connection_exit_2_both_files_written(tmp_path):
    code, report, paths, api, _ = go(tmp_path, starts={"broken": [ApiUnreachable("x")]})
    assert code == 2
    assert all(p.exists() for p in paths)
    assert {v["result"] for v in report["variants"]} == {"could_not_check"}
    assert api.calls_named("start_run") == ["broken"]  # no further request


def test_run_stuck_running_times_out_within_120_seconds(tmp_path):
    polls = {"broken": [running()], "fixed": [complete("PASSED")]}
    code, report, _, _, clock = go(tmp_path, polls=polls)
    assert code == 2
    assert by_variant(report)["broken"]["result"] == "could_not_check"
    assert 0 < clock.total_slept() <= 120


def test_retry_after_sleeps_exact_seconds_then_completes(tmp_path):
    starts = {"broken": [RateLimited("7"), "run-b"]}
    code, _, _, _, clock = go(tmp_path, starts=starts)
    assert code == 0 and clock.sleeps == [7]


def test_status_error_with_blocked_is_exit_2(tmp_path):
    polls = {"broken": GOOD["broken"], "fixed": [RunSnapshot("error", "BLOCKED", "X")]}
    code, report, _, _, _ = go(tmp_path, polls=polls)
    assert code == 2 and by_variant(report)["fixed"]["result"] == "could_not_check"


def test_broken_passed_is_could_not_check_not_ghost(tmp_path):
    polls = {"broken": [complete("PASSED")], "fixed": [complete("PASSED")]}
    code, report, paths, _, _ = go(tmp_path, polls=polls)
    entries = by_variant(report)
    assert code == 2 and entries["broken"]["result"] == "could_not_check"
    assert report["outcome"] != "returning_ghost"
    assert "returning ghost" not in paths[0].read_text(encoding="utf-8").lower()


def test_unexpected_exception_exit_2_and_names_type(tmp_path):
    code, report, paths, _, _ = go(tmp_path, starts={"broken": [RuntimeError("boom")]})
    assert code == 2
    assert "RuntimeError" in json.dumps(report)
    assert "RuntimeError" in paths[0].read_text(encoding="utf-8")


# ---- main() ----

def patch_main(monkeypatch, tmp_path, api):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HA_API_URL", raising=False)
    monkeypatch.setattr(rj, "ApiClient", lambda url: api)
    monkeypatch.setattr(rj, "_RealClock", FakeClock)


def test_report_write_failure_exit_2(monkeypatch, tmp_path, capsys):
    patch_main(monkeypatch, tmp_path, FakeApi(polls=GOOD))
    (tmp_path / "reports").write_text("a file, not a folder", encoding="utf-8")
    assert rj.main() == 2
    err = capsys.readouterr().err
    assert "reports" in err and "Could not" in err


@pytest.mark.parametrize("bad", ["ftp://x", "localhost:8000"])
def test_invalid_url_via_main(monkeypatch, tmp_path, capsys, bad):
    api = FakeApi(polls=GOOD)
    patch_main(monkeypatch, tmp_path, api)
    monkeypatch.setenv("HA_API_URL", bad)
    assert rj.main() == 2
    err = capsys.readouterr().err
    assert "HA_API_URL" in err and "http://" in err and "https://" in err
    assert api.calls == []
    assert not (tmp_path / "reports").exists()


def test_main_prints_exactly_one_summary_line(monkeypatch, tmp_path, capsys):
    patch_main(monkeypatch, tmp_path, FakeApi(polls=GOOD))
    assert rj.main() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "all_as_expected" in lines[0] and ".md" in lines[0]


# ---- 12.10 table: fixed-run status and verdict ----

@pytest.mark.parametrize("snap, starts, expected", [
    (complete("PASSED"), None, 0),
    (complete("BLOCKED", "FOCUS_TRAP"), None, 1),
    (RunSnapshot("error", "BLOCKED", "FOCUS_TRAP"), None, 2),
    (RunSnapshot("error", "PASSED", None), None, 2),
    (RunSnapshot("error", None, None), None, 2),
    (complete(None), None, 2),
    (complete("blocked"), None, 2),
    (complete("MAYBE"), None, 2),
    (RunSnapshot("weird", "PASSED", None), None, 2),
    (running(), None, 2),  # timeout
    (complete("PASSED"), {"fixed": [RateLimited("abc")]}, 2),  # unresolved 429
])
def test_fixed_run_exit_code_table(tmp_path, snap, starts, expected):
    polls = {"broken": GOOD["broken"], "fixed": [snap]}
    code, _, _, _, _ = go(tmp_path, starts=starts, polls=polls)
    assert code == expected


# ---- config and URLs ----

@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_url_gives_default(raw):
    assert normalize_api_url(raw) == DEFAULT_API_URL


def test_url_is_trimmed():
    assert normalize_api_url(" http://x/// ") == "http://x"


def test_ftp_url_rejected():
    with pytest.raises(ConfigError):
        normalize_api_url("ftp://x")


class ScriptSession:
    """Stub requests session: POSTs answered from a list, GETs always complete PASSED."""

    class Resp:
        def __init__(self, status=200, body=None, bad=False):
            self.status_code, self._body, self._bad = status, body, bad
            self.headers = {}

        def json(self):
            if self._bad:
                raise ValueError("bad json")
            return self._body

    def __init__(self, posts):
        self.posts, self.calls = list(posts), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "POST":
            return self.posts.pop(0) if len(self.posts) > 1 else self.posts[0]
        return self.Resp(200, {"status": "complete", "verdict": "PASSED", "reason_code": None})


def ok_post(run_id="run-9"):
    return ScriptSession.Resp(202, {"run_id": run_id})


def test_urls_have_no_double_slash_and_body_is_exact(tmp_path):
    session = ScriptSession([ok_post()])
    client = ApiClient(normalize_api_url(" http://127.0.0.1:8000// "), session=session)
    rj.run_check(client, FakeClock(), tmp_path, "http://127.0.0.1:8000", lambda: WHEN)
    for _, url, _ in session.calls:
        assert "//" not in url.split("://", 1)[1]
    posts = [kw for m, _, kw in session.calls if m == "POST"]
    assert [p["json"] for p in posts] == [
        {"variant": "broken", "mode": "scripted"},
        {"variant": "fixed", "mode": "scripted"},
    ]


# ---- Retry-After parsing ----

@pytest.mark.parametrize("raw, want", [
    ("5", 5), ("0", 0), ("120", 120),
    ("121", None), ("-1", None), ("1.5", None), ("", None), ("abc", None), (None, None),
])
def test_parse_retry_after(raw, want):
    assert parse_retry_after(raw) == want


# ---- judging ----

def test_judge_expected_results():
    assert judge("broken", complete("BLOCKED", "FOCUS_TRAP")).result == "as_expected"
    assert judge("fixed", complete("PASSED")).result == "as_expected"


def test_judge_ghost_keeps_reason_code():
    result = judge("fixed", complete("BLOCKED", "FOCUS_TRAP"))
    assert result.result == "returning_ghost" and result.reason_code == "FOCUS_TRAP"
    assert result.verdict == "BLOCKED"


def test_judge_ghost_without_reason_says_no_reason_given():
    assert judge("fixed", complete("BLOCKED", "")).reason_code == "no reason given"


@pytest.mark.parametrize("snap", [
    RunSnapshot("error", "PASSED", None),
    RunSnapshot("pending", "PASSED", None),
    complete("blocked"),
    complete(None),
])
def test_judge_unusable_snapshots(snap):
    assert judge("fixed", snap).result == "could_not_check"


# ---- polling ----

def test_polling_two_running_then_complete(tmp_path):
    polls = {"broken": [running(), running(), complete("BLOCKED", "FOCUS_TRAP")],
             "fixed": [complete("PASSED")]}
    code, _, _, api, clock = go(tmp_path, polls=polls)
    assert code == 0
    assert len([c for c in api.calls if c == ("get_run", "run-1")]) == 3
    assert clock.sleeps == [2, 2]


# ---- rate limit ----

def test_three_429s_then_accepted(tmp_path):
    starts = {"broken": [RateLimited("1"), RateLimited("2"), RateLimited("3"), "run-b"]}
    code, report, _, _, clock = go(tmp_path, starts=starts)
    assert code == 0 and clock.sleeps == [1, 2, 3]
    assert "waited 1 s" in by_variant(report)["broken"]["explanation"]


def test_fourth_429_gives_could_not_check_and_fixed_still_checked(tmp_path):
    starts = {"broken": [RateLimited("1")]}  # last item repeats
    code, report, _, api, clock = go(tmp_path, starts=starts)
    entries = by_variant(report)
    assert code == 2 and clock.sleeps == [1, 1, 1]
    assert entries["broken"]["result"] == "could_not_check"
    assert entries["fixed"]["result"] == "as_expected"
    assert api.calls_named("start_run") == ["broken"] * 4 + ["fixed"]


@pytest.mark.parametrize("header", [None, "abc", "121"])
def test_unusable_retry_after_does_not_sleep(tmp_path, header):
    code, _, _, _, clock = go(tmp_path, starts={"broken": [RateLimited(header)]})
    assert code == 2 and clock.sleeps == []


# ---- sequencing ----

def test_broken_first_then_fixed_and_at_most_two_runs(tmp_path):
    _, _, _, api, _ = go(tmp_path)
    assert api.calls_named("start_run") == ["broken", "fixed"]
    assert api.calls.index(("start_run", "fixed")) > api.calls.index(("start_run", "broken"))


def test_broken_failure_does_not_change_fixed_result(tmp_path):
    _, report, _, _, _ = go(tmp_path, starts={"broken": [ApiBadResponse("500")]})
    entries = by_variant(report)
    assert entries["broken"]["result"] == "could_not_check"
    assert entries["fixed"]["result"] == "as_expected"


# ---- failures ----

@pytest.mark.parametrize("bad", [
    ScriptSession.Resp(500, {}),
    ScriptSession.Resp(202, None, bad=True),
    ScriptSession.Resp(202, {"other": 1}),
])
def test_bad_start_response_affects_only_that_variant(tmp_path, bad):
    session = ScriptSession([bad, ok_post("run-f")])
    client = ApiClient(URL, session=session)
    code, report, _ = rj.run_check(client, FakeClock(), tmp_path, URL, lambda: WHEN)
    entries = by_variant(report)
    assert code == 2
    assert entries["broken"]["result"] == "could_not_check"
    assert entries["fixed"]["result"] == "as_expected"


def test_three_poll_failures_in_a_row_affect_only_that_variant(tmp_path):
    polls = {"broken": [ApiBadResponse("x")], "fixed": [complete("PASSED")]}
    _, report, _, _, clock = go(tmp_path, polls=polls)
    entries = by_variant(report)
    assert entries["broken"]["result"] == "could_not_check"
    assert entries["fixed"]["result"] == "as_expected"
    assert clock.sleeps == [2, 2]


# ---- report content ----

def test_json_keys_and_timestamp(tmp_path):
    _, report, paths, _, _ = go(tmp_path)
    assert set(report) == {"checked_at", "api_url", "mode", "journey",
                           "outcome", "exit_code", "variants"}
    assert report["checked_at"].endswith("Z") and report["mode"] == "scripted"
    on_disk = json.loads(paths[1].read_text(encoding="utf-8"))
    assert on_disk == report


def test_markdown_labels_and_never_claims_wcag(tmp_path):
    polls = {"broken": GOOD["broken"], "fixed": [complete("BLOCKED", "WCAG compliant")]}
    _, _, paths, _, _ = go(tmp_path, polls=polls)
    text = paths[0].read_text(encoding="utf-8")
    assert "scripted mode" in text and NO_AI_SENTENCE in text
    assert "wcag" not in text.lower()


def test_unknown_reason_code_is_quoted(tmp_path):
    polls = {"broken": GOOD["broken"], "fixed": [complete("BLOCKED", "ODD_CODE")]}
    _, _, paths, _, _ = go(tmp_path, polls=polls)
    assert 'an unrecognised reason code ("ODD_CODE")' in paths[0].read_text(encoding="utf-8")


def test_writing_twice_same_date_keeps_only_second(tmp_path):
    folder = tmp_path / "not" / "yet" / "there"
    results = [judge("broken", complete("BLOCKED")), judge("fixed", complete("PASSED"))]
    write_report(build_report(WHEN, URL, results, 0), folder)
    second = build_report(WHEN, "http://127.0.0.1:9999", results, 0)
    md, js = write_report(second, folder)
    assert json.loads(js.read_text(encoding="utf-8"))["api_url"] == "http://127.0.0.1:9999"
    assert "9999" in md.read_text(encoding="utf-8")
    assert sorted(p.name for p in folder.iterdir()) == ["2026-01-02.json", "2026-01-02.md"]
