"""Night Watch MCP server: JSON-RPC 2.0 over stdio, one message per line."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_NAME = "night-watch"
SERVER_VERSION = "0.1.0"
TOOL_NAME = "run_night_watch"
MAX_LINE_BYTES = 1_048_576
DEFAULT_PROTOCOL = "2024-11-05"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Run the nightly Send Payment check (scripted mode) against the Haunted "
        "Audit API and return a plain-English summary."
    ),
    "inputSchema": {"type": "object", "properties": {}},
}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def format_summary(code: int, report: dict, report_path) -> str:
    """Build the text summary: outcome, exit code, variant explanations, path."""
    lines = [f"Outcome: {report['outcome']}", f"Exit code: {code}"]
    for item in report["variants"]:
        lines.append(f"{item['variant']}: {item['result']}. {item['explanation']}")
    lines.append(f"Report: {report_path}")
    return "\n".join(lines)


def handle_message(message, run_tool):
    """Map one parsed JSON-RPC message to a response dict (None for notifications).

    run_tool() takes no arguments and returns the text summary.
    """
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        req_id = message.get("id") if isinstance(message, dict) else None
        return _error(req_id, INVALID_REQUEST, "Invalid request")
    if "id" not in message:
        return None  # a notification never gets a reply
    req_id = message["id"]
    method = message["method"]
    params = message.get("params")
    if method == "initialize":
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        return _result(req_id, {
            "protocolVersion": asked if isinstance(asked, str) and asked else DEFAULT_PROTOCOL,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
        })
    if method == "tools/list":
        return _result(req_id, {"tools": [TOOL]})
    if method == "tools/call":
        name = params.get("name") if isinstance(params, dict) else None
        if name != TOOL_NAME:
            return _error(req_id, INVALID_PARAMS, f"Unknown tool: {name!r}")
        try:
            text = run_tool()
        except Exception as exc:  # the server must keep running
            return _error(req_id, INTERNAL_ERROR, f"The check failed: {type(exc).__name__}")
        return _result(req_id, {"content": [{"type": "text", "text": str(text)}]})
    return _error(req_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def _send(stdout, response: dict) -> None:
    """Write one protocol message as a single line."""
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()


def _read_line(stdin):
    """Return (line, too_long). Oversized lines are drained and flagged."""
    # Read at most limit + 2 characters: the text plus its line ending.
    line = stdin.readline(MAX_LINE_BYTES + 2)
    if not line:
        return None, False
    text = line.rstrip("\r\n")
    too_long = len(text.encode("utf-8", "replace")) > MAX_LINE_BYTES
    if too_long:
        while line and not line.endswith("\n"):  # skip the rest of the long line
            line = stdin.readline(MAX_LINE_BYTES)
    return line, too_long


def serve(stdin, stdout, stderr, run_tool) -> None:
    """Read lines until end of input, answer each one on stdout."""
    while True:
        line, too_long = _read_line(stdin)
        if line is None:
            return
        if too_long:
            print("Skipped a line over the size limit.", file=stderr)
            _send(stdout, _error(None, PARSE_ERROR, "Parse error: line too long"))
            continue
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _send(stdout, _error(None, PARSE_ERROR, "Parse error"))
            continue
        try:
            response = handle_message(message, run_tool)
        except Exception as exc:  # last-resort guard
            print(f"Unexpected {type(exc).__name__}: {exc}", file=stderr)
            response = _error(None, INTERNAL_ERROR, "Internal error")
        if response is not None:
            _send(stdout, response)


def default_run_tool() -> str:
    """Run the real check (real client, clock and config) and return the summary."""
    from night_watch.api_client import ApiClient
    from night_watch.config import read_api_url
    from night_watch.run_journeys import _RealClock, run_check

    api_url = read_api_url()
    code, report, paths = run_check(ApiClient(api_url), _RealClock(), Path("reports"), api_url)
    return format_summary(code, report, paths[0])


def main() -> int:
    """Serve on the real standard streams."""
    # Allow "python night_watch/mcp_server.py": put the project root on the path.
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    serve(sys.stdin, sys.stdout, sys.stderr, default_run_tool)
    return 0


if __name__ == "__main__":
    sys.exit(main())
