# Night Watch: a Kiro Crew app built for Kiroween 2026

## What it does

- Every night it re-runs the Haunted Audit Send Payment journey in scripted mode.
- The broken variant must be BLOCKED and the fixed variant must PASS.
- If the fixed page breaks again, it reports a "returning ghost" in plain English.

## Proof

- [Returning ghost, terminal](docs/screenshots/nw4-returning-ghost-terminal.png)
- [Returning ghost, report](docs/screenshots/nw4-returning-ghost-report.md)
- [Restored, all as expected](docs/screenshots/nw4-restored-all-as-expected.png)
- 94 tests pass.

## How it was built with Kiro

- Spec in `.kiro/specs/night-watch`.
- Steering files in `.kiro/steering`.
- A test-on-save hook.
- An MCP server (FastMCP), called from Kiro IDE chat.

## Install

1. Create a Python 3.13 virtual environment.
2. `pip install -r requirements.txt`
3. Set `HA_API_URL` to the Haunted Audit API address, then run:
   `python -m night_watch.run_journeys`
4. To use it in Kiro Crew, install it from the `night_watch` folder.
5. Run the tests: `python -m pytest -q night_watch/tests`

## Known limitation

In Kiro Crew 0.13.1 on Windows, the app installs, is trusted and its nightly job runs. Crew's agent could not reach the app's MCP server (gateway log: `mcp_gateway=off`), so the agent reports "could not check" instead of guessing. The same tool works from Kiro IDE.

## Licence

MIT
