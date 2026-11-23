"""Build, render and write the nightly report (Markdown and JSON)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from night_watch.judge import outcome_for
from night_watch.models import (
    COULD_NOT_CHECK,
    EXPECTED,
    RETURNING_GHOST,
    VariantResult,
)

MAX_EXPLANATION = 500

# Fixed plain-English sentences for the reason codes in the API contract.
REASON_TEXT = {
    "TARGET_NOT_FOCUSABLE": "the pay button could not be reached with the keyboard",
    "FOCUS_TRAP": "keyboard focus got stuck and could not move on",
    "NO_ACTIVATION": "the pay button did not respond when it was activated",
    "STEP_LIMIT": "the script ran out of steps before it finished",
    "TIMEOUT": "the page took too long to respond",
}

NO_AI_SENTENCE = (
    "Scripted mode follows a fixed script and uses no AI model to drive the journey."
)

_WCAG = re.compile(r"wcag", re.IGNORECASE)


def _clean(text: str) -> str:
    """Remove the word WCAG from text that came from outside, so reports never carry it."""
    return _WCAG.sub("[removed]", text)


def _one_line(text: str) -> str:
    """Collapse whitespace so quoted API values stay on one line."""
    return " ".join(text.split())


def describe_reason(code: str | None) -> str:
    """Return a fixed sentence for a known code, or a quoted marker for an unknown one."""
    if code is None or code == "no reason given":
        return "no reason was given"
    if code in REASON_TEXT:
        return REASON_TEXT[code]
    return f'an unrecognised reason code ("{_clean(_one_line(code))}")'


def _utc_text(checked_at: datetime) -> str:
    """UTC ISO-8601 text ending in Z, with whole seconds."""
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    utc = checked_at.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry(result: VariantResult) -> dict:
    """One variants entry with exactly the required fields."""
    explanation = _clean(result.explanation).strip()[:MAX_EXPLANATION]
    reason = result.reason_code
    return {
        "variant": result.variant,
        "expected_verdict": EXPECTED[result.variant],
        "run_id": result.run_id,
        "status": result.status,
        "verdict": result.verdict,
        "reason_code": _clean(reason) if isinstance(reason, str) else reason,
        "result": result.result,
        "explanation": explanation or "No explanation available.",
    }


def build_report(
    checked_at: datetime, api_url: str, results: Sequence[VariantResult], exit_code: int
) -> dict:
    """Build the report dict. Variants are always listed broken first, then fixed."""
    by_name = {r.variant: r for r in results}
    return {
        "checked_at": _utc_text(checked_at),
        "api_url": api_url,
        "mode": "scripted",
        "journey": "send-payment",
        "outcome": outcome_for(results),
        "exit_code": exit_code,
        "variants": [_entry(by_name[name]) for name in ("broken", "fixed")],
    }


def render_markdown(report: dict) -> str:
    """Turn a report dict into plain-English Markdown."""
    lines = [
        f"# Night Watch report, {report['checked_at'][:10]}",
        "",
        f"Checked at {report['checked_at']} against {_clean(str(report['api_url']))}.",
        "This check ran in scripted mode. " + NO_AI_SENTENCE,
        "",
        f"Outcome: {report['outcome']} (exit code {report['exit_code']})",
        "",
    ]
    for entry in report["variants"]:
        name = entry["variant"]
        lines.append(f"## {name.capitalize()} variant")
        if entry["result"] == RETURNING_GHOST:
            reason = entry["reason_code"] or "no reason given"
            lines.append(
                f"A returning ghost: the fixed variant was blocked, reason code {reason}, "
                f"which means {describe_reason(entry['reason_code'])}."
            )
        elif entry["result"] == COULD_NOT_CHECK:
            lines.append(
                f"Could not check the {name} variant. Cause: {_clean(entry['explanation'])}"
            )
        else:
            lines.append(_clean(entry["explanation"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: dict, reports_dir: Path) -> tuple[Path, Path]:
    """Write both files, replacing any earlier ones for the same UTC date."""
    reports_dir = Path(reports_dir)
    date = report["checked_at"][:10]
    md_path = reports_dir / f"{date}.md"
    json_path = reports_dir / f"{date}.json"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Could not create the reports folder {reports_dir}: {exc.strerror or exc}") from exc
    for path, text in (
        (md_path, render_markdown(report)),
        (json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
    ):
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError as exc:
            raise OSError(f"Could not write {path}: {exc.strerror or exc}") from exc
    return md_path, json_path
