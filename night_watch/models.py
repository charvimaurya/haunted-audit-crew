"""Shared data shapes and constants for Night Watch results."""
from __future__ import annotations

from dataclasses import dataclass

# The two variants of the Send Payment journey, in the order they are checked.
VARIANTS = ("broken", "fixed")

# What each variant should come back as.
EXPECTED = {"broken": "BLOCKED", "fixed": "PASSED"}

# Result labels for one variant.
AS_EXPECTED = "as_expected"
RETURNING_GHOST = "returning_ghost"
COULD_NOT_CHECK = "could_not_check"

# Explanation used when the broken variant unexpectedly passes.
BROKEN_STILL_PASSES = (
    "Broken variant no longer blocks: the checker or test page changed"
)


@dataclass(frozen=True)
class RunSnapshot:
    """One GET /runs/{id} answer. Values are kept exactly as received."""

    status: object
    verdict: object
    reason_code: object


@dataclass(frozen=True)
class VariantResult:
    """The outcome of checking one variant."""

    variant: str  # "broken" or "fixed"
    run_id: str | None
    status: str | None
    verdict: str | None
    reason_code: str | None
    result: str  # as_expected, returning_ghost or could_not_check
    explanation: str  # plain English, 1 to 500 characters
