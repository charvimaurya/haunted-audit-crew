"""Property test for exit code and outcome priority (synthetic data only)."""
from hypothesis import given, settings, strategies as st

from night_watch.judge import exit_code_for, judge, outcome_for
from night_watch.models import (
    AS_EXPECTED,
    COULD_NOT_CHECK,
    RETURNING_GHOST,
    RunSnapshot,
    VariantResult,
)

LABELS = [AS_EXPECTED, RETURNING_GHOST, COULD_NOT_CHECK]


def _result(variant: str, label: str) -> VariantResult:
    """Build a synthetic result with the given label."""
    return VariantResult(variant, None, None, None, None, label, "Synthetic result.")


# Statuses and verdicts, including odd values that must never be trusted.
statuses = st.one_of(
    st.sampled_from(["complete", "error", "running", "queued", "Complete", ""]),
    st.none(),
    st.text(max_size=8),
)
verdicts = st.one_of(
    st.sampled_from(["PASSED", "BLOCKED", "passed", "blocked", "UNKNOWN", ""]),
    st.none(),
    st.text(max_size=8),
)


# Feature: night-watch, Property 1: Exit code and outcome priority
# **Validates: Requirements 7.1, 7.2, 7.3, 7.6, 12.10**
@settings(max_examples=100)
@given(
    broken_label=st.sampled_from(LABELS),
    fixed_label=st.sampled_from(LABELS),
    status=statuses,
    verdict=verdicts,
    reason=st.one_of(st.none(), st.text(max_size=10)),
    broken_status=statuses,
)
def test_exit_code_and_outcome_priority(
    broken_label, fixed_label, status, verdict, reason, broken_status
):
    # Priority over any pair of results.
    results = [_result("broken", broken_label), _result("fixed", fixed_label)]
    labels = {broken_label, fixed_label}
    code = exit_code_for(results)
    assert code in {0, 1, 2}
    if RETURNING_GHOST in labels:
        assert code == 1 and outcome_for(results) == "returning_ghost"
    elif COULD_NOT_CHECK in labels:
        assert code == 2 and outcome_for(results) == "could_not_check"
    else:
        assert code == 0 and outcome_for(results) == "all_as_expected"

    # Fixed-run rule: judge the fixed variant, then take the exit code.
    fixed = judge("fixed", RunSnapshot(status, verdict, reason))
    fixed_code = exit_code_for([fixed])
    if status == "complete" and verdict == "BLOCKED":
        assert fixed_code == 1
    elif status == "complete" and verdict == "PASSED":
        assert fixed_code == 0
    else:
        # error status, null verdict, or any other verdict or status
        assert fixed_code == 2

    # Broken + PASSED gives exit 2 and never a returning ghost.
    broken = judge("broken", RunSnapshot("complete", "PASSED", reason))
    assert broken.result != RETURNING_GHOST
    assert exit_code_for([broken]) == 2
    # An errored broken run never produces a ghost either.
    other = judge("broken", RunSnapshot(broken_status, "PASSED", None))
    assert other.result != RETURNING_GHOST
