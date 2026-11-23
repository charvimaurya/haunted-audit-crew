"""Pure judging of one run, plus exit code and outcome rules."""
from __future__ import annotations

from typing import Sequence

from night_watch.models import (
    AS_EXPECTED,
    BROKEN_STILL_PASSES,
    COULD_NOT_CHECK,
    EXPECTED,
    RETURNING_GHOST,
    RunSnapshot,
    VariantResult,
)

NO_REASON = "no reason given"
MAX_EXPLANATION = 500


def _clip(text: str) -> str:
    """Keep an explanation between 1 and 500 characters."""
    text = text.strip() or "No explanation available."
    return text[:MAX_EXPLANATION]


def _unchecked(variant: str, status: object, text: str) -> VariantResult:
    """Build a could_not_check result. No verdict is carried."""
    return VariantResult(
        variant=variant,
        run_id=None,
        status=status if isinstance(status, str) else None,
        verdict=None,
        reason_code=None,
        result=COULD_NOT_CHECK,
        explanation=_clip(text),
    )


def judge(variant: str, snapshot: RunSnapshot) -> VariantResult:
    """Apply the expected-outcome rules to one snapshot.

    The status is checked first. The verdict is only read when the status
    is exactly "complete" and the verdict is exactly PASSED or BLOCKED.
    """
    status, verdict = snapshot.status, snapshot.verdict

    if status == "error":
        return _unchecked(variant, status, f"The {variant} run ended with an error, so it could not be checked.")
    if status != "complete":
        return _unchecked(variant, status, f"The {variant} run gave an unknown status, so it could not be checked.")
    if verdict not in ("PASSED", "BLOCKED"):
        return _unchecked(variant, status, f"The {variant} run finished without a usable verdict, so it could not be checked.")

    reason = snapshot.reason_code
    reason = reason if isinstance(reason, str) and reason else None

    def make(result: str, text: str, reason_code: str | None) -> VariantResult:
        return VariantResult(variant, None, status, verdict, reason_code, result, _clip(text))

    if variant == "broken" and verdict == "PASSED":
        return _unchecked(variant, status, BROKEN_STILL_PASSES)
    if verdict == EXPECTED.get(variant):
        word = "blocked" if verdict == "BLOCKED" else "passed"
        return make(AS_EXPECTED, f"The {variant} variant {word}, as expected.", reason)
    # Only fixed + BLOCKED is left: a returning ghost.
    shown = reason or NO_REASON
    return make(
        RETURNING_GHOST,
        f"Returning ghost: the fixed variant was blocked. Reason code: {shown}.",
        shown,
    )


def outcome_for(results: Sequence[VariantResult]) -> str:
    """Name the overall outcome: ghost first, then could-not-check."""
    if any(r.result == RETURNING_GHOST for r in results):
        return "returning_ghost"
    if any(r.result == COULD_NOT_CHECK for r in results):
        return "could_not_check"
    return "all_as_expected"


def exit_code_for(results: Sequence[VariantResult]) -> int:
    """1 if any returning ghost, else 2 if any could not check, else 0."""
    return {"returning_ghost": 1, "could_not_check": 2}.get(outcome_for(results), 0)
