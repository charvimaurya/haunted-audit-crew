"""Scheduled accessibility journey checks (scripted mode only)."""
from __future__ import annotations

import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from night_watch.api_client import ApiBadResponse, ApiClient, ApiUnreachable, RateLimited
from night_watch.config import ConfigError, read_api_url
from night_watch.judge import MAX_EXPLANATION, exit_code_for, judge
from night_watch.models import COULD_NOT_CHECK, VARIANTS, VariantResult
from night_watch.report import build_report, write_report
from night_watch.retry import parse_retry_after

POLL_INTERVAL = 2  # seconds between polls
RUN_TIMEOUT = 120  # seconds allowed for one run
MAX_RETRIES = 3  # retries after a 429
MAX_POLL_FAILURES = 3  # failed polls in a row before giving up


class _Unreachable(Exception):
    """Internal: the API cannot be reached, so stop sending requests."""

    def __init__(self, run_id=None):
        super().__init__("unreachable")
        self.run_id = run_id


def _could_not_check(variant, text, run_id=None, status=None) -> VariantResult:
    """Build a could_not_check result with a clipped, non-empty explanation."""
    text = text.strip() or "Could not check this variant."
    return VariantResult(
        variant, run_id, status, None, None, COULD_NOT_CHECK, text[:MAX_EXPLANATION]
    )


def _start(client, clock, variant, notes):
    """POST /runs with the 429 loop. Returns (run_id, None) or (None, result)."""
    retries = 0
    while True:
        try:
            return client.start_run(variant), None
        except RateLimited as exc:
            wait = parse_retry_after(exc.retry_after)
            if wait is None:
                notes.append("The Retry-After value was unusable.")
                return None, "rate limited"
            if retries >= MAX_RETRIES:
                notes.append(
                    f"The rate-limit retry limit of {MAX_RETRIES} retries was reached."
                )
                return None, "rate limited"
            retries += 1
            clock.sleep(wait)
            notes.append(f"waited {wait} s before retry {retries} of {MAX_RETRIES}")
        except ApiUnreachable:
            raise _Unreachable()
        except ApiBadResponse as exc:
            notes.append(f"The API gave a bad response when starting the run ({exc}).")
            return None, "bad response"


def _poll(client, clock, variant, run_id, notes):
    """Poll until a terminal snapshot. Returns a VariantResult."""
    began = clock.now()
    failures = 0
    while True:
        try:
            snapshot = client.get_run(run_id)
            failures = 0
        except ApiUnreachable:
            raise _Unreachable(run_id)
        except (ApiBadResponse, RateLimited) as exc:
            failures += 1
            if failures >= MAX_POLL_FAILURES:
                return _could_not_check(
                    variant,
                    f"The {variant} run could not be checked: status polls failed "
                    f"{MAX_POLL_FAILURES} times in a row ({exc}).",
                    run_id,
                )
            snapshot = None
        if snapshot is not None and snapshot.status != "running":
            result = judge(variant, snapshot)
            return replace(result, run_id=run_id)
        # Give up if the next sleep would pass the time limit.
        if (clock.now() - began) + POLL_INTERVAL > RUN_TIMEOUT:
            return _could_not_check(
                variant, f"The {variant} run timed out after {RUN_TIMEOUT} seconds.",
                run_id, "running",
            )
        clock.sleep(POLL_INTERVAL)


def _check_variant(client, clock, variant) -> VariantResult:
    """Check one variant. Raises _Unreachable if the API cannot be reached."""
    notes: list[str] = []
    run_id, failed = _start(client, clock, variant, notes)
    if failed:
        text = f"The {variant} variant could not be checked: {failed}. " + " ".join(notes)
        return _could_not_check(variant, text)
    result = _poll(client, clock, variant, run_id, notes)
    waits = [n for n in notes if n.startswith("waited")]
    if waits:
        text = (result.explanation + " (" + "; ".join(waits) + ")")[:MAX_EXPLANATION]
        result = replace(result, explanation=text)
    return result


def _finish(done, api_url, now_fn, reports_dir, exit_code=None):
    """Build and write the report for the results collected so far."""
    code = exit_code_for(done) if exit_code is None else exit_code
    report = build_report(now_fn(), api_url, done, code)
    return code, report, write_report(report, reports_dir)


def run_check(
    client, clock, reports_dir: Path, api_url: str,
    now_fn=lambda: datetime.now(timezone.utc),
) -> tuple[int, dict, tuple[Path, Path]]:
    """Check both variants in order, write the report, return code, report, paths."""
    done: dict[str, VariantResult] = {}
    try:
        for variant in VARIANTS:
            try:
                done[variant] = _check_variant(client, clock, variant)
            except _Unreachable as exc:
                done[variant] = _could_not_check(
                    variant,
                    f"The API could not be reached while checking the {variant} variant.",
                    exc.run_id,
                )
                for rest in VARIANTS[len(done):]:
                    done[rest] = _could_not_check(
                        rest, f"The API could not be reached, so the {rest} variant was not checked."
                    )
                break
        return _finish(list(done.values()), api_url, now_fn, reports_dir)
    except Exception as exc:  # catch-all: report it and exit with code 2
        kind = type(exc).__name__
        for variant in VARIANTS:
            if variant not in done:
                done[variant] = _could_not_check(
                    variant,
                    f"Unexpected {kind}: the check stopped because of an internal "
                    f"error ({str(exc) or 'no details'}).",
                )
        return _finish(list(done.values()), api_url, now_fn, reports_dir, exit_code=2)


class _RealClock:
    """The real clock: wall-free monotonic time and a real sleep."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def main(argv=None) -> int:
    """Run the nightly check, print one summary line, and return the exit code."""
    reports_dir = Path("reports")
    try:
        try:
            api_url = read_api_url()
        except ConfigError:
            print(
                "HA_API_URL is invalid: it must begin with http:// or https://",
                file=sys.stderr,
            )
            return 2
        client = ApiClient(api_url)
        try:
            code, report, paths = run_check(client, _RealClock(), reports_dir, api_url)
        except OSError as exc:
            # The report could not be written: name the path and the cause.
            target = getattr(exc, "filename", None) or reports_dir
            print(
                f"Could not write the report to {target}: {exc.strerror or exc}",
                file=sys.stderr,
            )
            return 2
        print(f"Night Watch: {report['outcome']}. Report: {paths[0]}")
        return code
    except Exception as exc:  # catch-all: never let an exception escape
        print(f"Night Watch failed with {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
