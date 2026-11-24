"""Night Watch MCP server (official `mcp` package, FastMCP, stdio)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

# Crew may install this folder under any name (e.g. "night-watch"), so
# register the folder itself as the package "night_watch". Imports like
# "night_watch.config" then work whatever the folder is called.
HERE = Path(__file__).resolve().parent
if "night_watch" not in sys.modules:
    _pkg = types.ModuleType("night_watch")
    _pkg.__path__ = [str(HERE)]
    sys.modules["night_watch"] = _pkg

# Reports are written next to this file.
REPORTS_DIR = HERE / "reports"

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("night-watch")


def build_summary(code: int, report: dict, report_path) -> str:
    """Build the text summary: outcome, exit code, variant explanations, path."""
    lines = [f"Outcome: {report['outcome']}", f"Exit code: {code}"]
    for item in report["variants"]:
        lines.append(f"{item['variant']}: {item['result']}. {item['explanation']}")
    lines.append(f"Report: {report_path}")
    return "\n".join(lines)


def default_runner() -> str:
    """Run the real check (real client, clock and config) and return the summary."""
    from night_watch.api_client import ApiClient
    from night_watch.config import read_api_url
    from night_watch.run_journeys import _RealClock, run_check

    api_url = read_api_url()
    code, report, paths = run_check(
        ApiClient(api_url), _RealClock(), REPORTS_DIR, api_url
    )
    return build_summary(code, report, paths[0])


def run_night_watch(runner=None) -> str:
    """Run the nightly Send Payment check (scripted mode) and return a summary.

    Exit codes 1 and 2 are normal results, not errors. The optional runner
    argument lets tests inject a stub; the MCP tool itself takes no arguments.
    """
    try:
        return (runner or default_runner)()
    except Exception as exc:  # report the failure instead of crashing the server
        print(f"Night Watch check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return f"The check could not be run: {type(exc).__name__}. No verdict is available."


@mcp.tool(name="run_night_watch")
def _run_night_watch_tool() -> str:
    """Run the nightly Send Payment check (scripted mode, no AI model) and return a plain-English summary."""
    return run_night_watch()


def main() -> None:
    """Serve over stdio. The package owns stdout; diagnostics go to stderr."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
