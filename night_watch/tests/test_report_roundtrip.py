"""Property test: the report JSON file reads back as an equal dict."""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from hypothesis import given, settings, strategies as st

from night_watch.judge import exit_code_for
from night_watch.models import (
    AS_EXPECTED,
    COULD_NOT_CHECK,
    RETURNING_GHOST,
    VariantResult,
)
from night_watch.report import build_report, write_report

# Any text (including non-ASCII) except lone surrogates, which UTF-8 cannot hold.
_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)))
_optional = st.none() | _text
_explanation = _text.filter(lambda s: 1 <= len(s) <= 500)


def _result(variant: str):
    """Strategy for one synthetic VariantResult of the given variant."""
    return st.builds(
        VariantResult,
        variant=st.just(variant),
        run_id=_optional,
        status=_optional,
        verdict=_optional,
        reason_code=_optional,
        result=st.sampled_from([AS_EXPECTED, RETURNING_GHOST, COULD_NOT_CHECK]),
        explanation=_explanation,
    )


@given(
    broken=_result("broken"),
    fixed=_result("fixed"),
    checked_at=st.datetimes(
        min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(timezone.utc)
    ),
)
@settings(max_examples=100)
def test_report_json_round_trip(broken, fixed, checked_at):
    # Feature: night-watch, Property 2: Report JSON round trip
    # Validates: Requirements 8.12, 12.11
    results = [broken, fixed]
    report = build_report(checked_at, "http://127.0.0.1:8000", results, exit_code_for(results))
    with tempfile.TemporaryDirectory() as tmp:
        _md_path, json_path = write_report(report, Path(tmp) / "reports")
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded == report
