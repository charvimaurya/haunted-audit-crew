"""Small MCP tests: call run_night_watch directly with a runner stub."""
import pytest

from night_watch.mcp_server import build_summary, run_night_watch

# Synthetic reports only: outcome, per-variant result and explanation.
CASES = [
    (0, "healthy", "FAIL", "PASS"),
    (1, "returning_ghost", "FAIL", "FAIL"),
    (2, "could_not_check", "could_not_check", "could_not_check"),
]


def _stub_for(code, outcome, broken, fixed, path):
    report = {
        "outcome": outcome,
        "variants": [
            {"variant": "broken", "result": broken, "explanation": f"broken note {code}"},
            {"variant": "fixed", "result": fixed, "explanation": f"fixed note {code}"},
        ],
    }
    return lambda: build_summary(code, report, path)


@pytest.mark.parametrize("code,outcome,broken,fixed", CASES)
def test_summary_has_outcome_code_explanations_and_path(code, outcome, broken, fixed):
    path = "reports/2026-01-01.md"
    summary = run_night_watch(_stub_for(code, outcome, broken, fixed, path))
    assert outcome in summary
    assert f"Exit code: {code}" in summary
    assert f"broken note {code}" in summary
    assert f"fixed note {code}" in summary
    assert path in summary


def test_raising_stub_gives_error_message_without_crashing():
    def boom():
        raise RuntimeError("synthetic failure")

    summary = run_night_watch(boom)
    assert "could not be run" in summary
    assert "RuntimeError" in summary
    assert "No verdict" in summary
