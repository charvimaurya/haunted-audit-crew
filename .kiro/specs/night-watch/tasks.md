# Implementation Plan: Night Watch

## Overview

Python 3.12+, standard library plus `requests`, tests with pytest and Hypothesis. The work follows the design's module split: small pure modules first (config, retry, models, judge), then the API client, report, runner, MCP server, and finally the Kiro Crew manifest, skill and prompt. Every module is wired into the runner or server in the same plan, so no code is left orphaned.

Only two Hypothesis tests are kept: exit code priority (2.4) and the report JSON round trip (5.5). Every other behaviour is covered by small example tests, mostly in `night_watch/tests/test_run_journeys.py` (6.7). All test data is synthetic, and no test opens a network connection or waits in real time.

## Tasks

- [x] 1. Build the pure foundation modules
  - [x] 1.1 Implement `night_watch/config.py`
    - Add `DEFAULT_API_URL`, `ConfigError`, `normalize_api_url()` and `read_api_url()` reading `HA_API_URL`
    - Blank or missing gives the default. Strip whitespace and trailing slashes. Reject anything not starting with `http://` or `https://`
    - Use plain-English comments and no secrets
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.3 Implement `night_watch/retry.py`
    - Add `parse_retry_after()`: digits-only whole number 0..120 returns an int, everything else (including None) returns None
    - _Requirements: 5.1, 5.3_

  - [x] 1.5 Implement `night_watch/models.py`
    - Add `VARIANTS`, `EXPECTED`, frozen dataclasses `RunSnapshot` and `VariantResult`
    - Add result constants `as_expected`, `returning_ghost`, `could_not_check`
    - Add the constant `BROKEN_STILL_PASSES` with the exact value "Broken variant no longer blocks: the checker or test page changed"
    - _Requirements: 3.3, 4.1, 4.2, 4.4, 8.6_

- [ ] 2. Implement judging and exit codes
  - [x] 2.1 Implement `night_watch/judge.py`
    - Add `judge()`, `exit_code_for()` and `outcome_for()` exactly as in the design table
    - Check status before verdict. Keep `reason_code` and `verdict` unchanged. Ghost with no reason code records "no reason given"
    - Broken + PASSED gives could_not_check (exit code 2) with the explanation `BROKEN_STILL_PASSES`, exactly "Broken variant no longer blocks: the checker or test page changed". It is never a returning ghost (assumption A4, confirmed)
    - Every explanation is plain English, 1 to 500 characters
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.1, 7.2, 7.3_

  - [ ] 2.4 Write property test for exit code and outcome priority (pure part)
    - File: `night_watch/tests/test_exit_codes.py`
    - **Property 1: Exit code and outcome priority** (Hypothesis test 1 of 2)
    - Cover `exit_code_for` and `outcome_for` over result pairs (1 if any ghost, else 2 if any could_not_check, else 0, always in {0, 1, 2})
    - Also cover the fixed-run rule (12.10): exit 1 if and only if the fixed run has status `complete` and verdict `BLOCKED`. Exit 2 for status `error` (any verdict), an unresolved 429, a timeout, a null verdict, or any verdict other than `PASSED` or `BLOCKED`. Exit 0 only when the fixed run is `complete` with verdict `PASSED`
    - Also cover broken + PASSED giving exit code 2 and no returning ghost
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.6, 12.10**

- [x] 3. Implement the API client
  - [x] 3.1 Implement `night_watch/api_client.py`
    - Add `ApiUnreachable`, `ApiBadResponse`, `RateLimited` (with raw `retry_after`) and `ApiClient(base_url, session=None, timeout=10.0)`
    - `start_run` posts exactly `{"variant": variant, "mode": "scripted"}`, expects 202 with `run_id`, maps 429 to `RateLimited`, other failures to `ApiBadResponse`, and connection errors and timeouts to `ApiUnreachable`
    - `get_run` returns a `RunSnapshot` with values as received. Build URLs as `base_url + "/runs"`
    - _Requirements: 1.3, 2.1, 2.2, 2.4, 2.7, 6.1, 6.3, 6.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement the report
  - [x] 5.1 Implement `night_watch/report.py`
    - Add `build_report()`, `render_markdown()` and `write_report()` using `pathlib`
    - Report fields exactly as in the design. `checked_at` ends in `Z`. File names come from the UTC date. Create the folder, overwrite both files, write UTF-8 JSON with `ensure_ascii=False`
    - Map known reason codes to fixed plain-English sentences. Show unknown codes as "an unrecognised reason code" with the code quoted. Never put API free text in prose
    - Markdown contains "scripted mode" and a sentence that scripted mode follows a fixed script and uses no AI model. It never uses "WCAG" with compliance wording. Ghost sentence names the fixed variant and reason code. Could_not_check entries show variant name and cause
    - Raise a clear error that names the path and cause when writing fails
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.12_

  - [x] 5.2 Implement the test fakes in `night_watch/tests/fakes.py`
    - `FakeApi` with a scripted list of responses or exceptions per variant and a call log, no network
    - `FakeClock` where `sleep` records the duration and advances `now`
    - Synthetic data only (run ids like `run-1`, `127.0.0.1` URLs)
    - _Requirements: 12.2, 12.3, 12.14_

  - [ ] 5.5 Write property test for JSON round trip
    - File: `night_watch/tests/test_report_roundtrip.py`
    - **Property 2: Report JSON round trip** (Hypothesis test 2 of 2)
    - **Validates: Requirements 8.12, 12.11**

- [ ] 6. Implement the runner
  - [x] 6.1 Implement `run_check()` in `night_watch/run_journeys.py`
    - Inject `ApiClient`, `Clock`, reports folder, API URL and a `now_fn`
    - Check broken then fixed, one at a time. Poll every 2 s up to 120 s total. Stop after three poll failures in a row
    - Run the 429 loop: up to 3 retries, wait exactly the `Retry-After` seconds, record each wait in the explanation, unusable header or fourth 429 gives could_not_check, and the other variant is still attempted
    - On `ApiUnreachable`, mark this and all unchecked variants could_not_check and send no more requests. On `ApiBadResponse`, affect only this variant
    - Wrap in a catch-all that builds a report with the exception type and a plain description, and returns exit code 2
    - Build the report, write both files, return `(exit_code, report, paths)`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.7, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.4_

  - [x] 6.2 Implement `main()` in `night_watch/run_journeys.py`
    - Read config. On `ConfigError` (bad `HA_API_URL`, Requirement 1.4) print "HA_API_URL is invalid: it must begin with http:// or https://" to stderr and return exit code 2 before any request. No report is written in this case, because no check ran
    - Build the real `ApiClient` and clock, call `run_check`, print exactly one summary line with the outcome and the Markdown path, return the exit code
    - Catch every exception and return 2. If the report cannot be written, print one stderr line naming the path and cause, and return 2
    - Add the `if __name__ == "__main__"` entry point using `sys.exit(main())`
    - _Requirements: 1.1, 1.4, 6.6, 7.4, 7.5, 7.6, 8.3, 8.11_

  - [ ] 6.7 Write example tests in `night_watch/tests/test_run_journeys.py`
    - Cases: broken BLOCKED and fixed PASSED gives exit 0. Fixed BLOCKED gives exit 1 and "returning ghost" in the Markdown. Refused connection gives exit 2 and both files exist. A run stuck in `running` gives exit 2 with at most 120 s of fake sleep. A 429 with `Retry-After: N` sleeps exactly N and then completes. Status `error` with verdict BLOCKED gives exit 2. Broken variant returning PASSED gives exit 2, `could_not_check` for broken, and no returning ghost (4.4, 7.3)
    - Also test: unexpected exception gives exit 2 and a report naming the exception type, report-write failure gives exit 2, invalid `HA_API_URL` (for example `ftp://x` or `localhost:8000`) sends no request, prints an error naming `HA_API_URL` and stating it must begin with `http://` or `https://`, writes no report, and exits with code 2 (1.4), and `main()` prints exactly one summary line
    - Add a parametrized table (not Hypothesis) over fixed-run status and verdict (12.10): exit 1 only for `complete` + `BLOCKED`. Exit 2 for status `error`, an unresolved 429, a timeout, a null verdict or any other verdict. Exit 0 only for `complete` + `PASSED`
    - Key cases moved from the removed property tests, each as a small example:
      - Config and URLs: blank and whitespace give the default, ` http://x/// ` gives `http://x`, `ftp://x` is rejected. Request URLs have no `//` after the host, and the POST body is exactly `{"variant": ..., "mode": "scripted"}` (1.2, 1.3, 2.1, 2.2)
      - Retry-After: "5", "0" and "120" give numbers. "121", "-1", "1.5", "", "abc" and None give None (5.1, 5.3)
      - Judging: broken BLOCKED and fixed PASSED are as expected. Fixed BLOCKED is a ghost with the reason code unchanged, or "no reason given" when it is empty. Status `error` with PASSED, an unknown status, verdict `blocked` in lowercase and a None verdict are all could_not_check (3.x, 4.x)
      - Polling: two `running` answers then `complete` give 3 GET calls and two sleeps of 2 s (2.4, 2.5)
      - Rate limit: three 429s with `Retry-After` 1, 2, 3 then a 202 sleep exactly 1, 2, 3 and complete. A fourth 429 gives could_not_check and the fixed variant is still checked. An unusable header gives no sleep (5.x)
      - Sequencing: the broken POST comes before the fixed POST, never more than 2 runs start, and a failure on broken does not change the fixed result (2.3, 2.6, 5.4)
      - Failures: HTTP 500, invalid JSON, a missing `run_id` and three poll failures in a row each give could_not_check for that variant only. A refused connection on broken also marks fixed could_not_check with no further request (2.7, 2.8, 6.x)
      - Report: JSON has exactly the required keys and `checked_at` ends in `Z`. Markdown contains "scripted mode" and the no-AI-model sentence, and never "WCAG" next to a compliance word even with a hostile reason code. An unknown reason code is shown quoted. Writing twice for the same date into a folder that does not exist yet leaves only the second report (8.x)
    - _Requirements: 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.13, 12.14_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement the MCP server
  - [ ] 8.1 Implement `night_watch/mcp_server.py` with the official `mcp` package
    - Add `mcp` to the project requirements. Create `FastMCP("night-watch")`, register one tool function `run_night_watch()` that takes no arguments, and start it with the stdio transport in `main()`
    - The tool function calls `run_check` once with the real client, clock and config, and returns a text summary with the outcome, exit code, one explanation per variant, and the report path. Exit codes 1 and 2 are normal results. Put summary building in a small helper so a test can call the function directly
    - Write no JSON-RPC, framing, handshake or protocol-error code: the package handles all of it. Print nothing to stdout except through the package. Diagnostics go to stderr
    - This replaces the earlier hand-written server in the same file
    - Crew runs the server from inside night_watch/ as 'python mcp_server.py', so make that work despite the 'from night_watch...' imports (add the parent folder to sys.path at the top). Replace the old hand-written mcp_server.py completely.
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [ ] 8.5 Write a small MCP test
    - File: `night_watch/tests/test_mcp_examples.py`
    - Call the `run_night_watch` tool function directly with a runner stub, with no stdio and no protocol. Check that the summary holds the outcome, exit code, per-variant explanation and report path for stub exit codes 0, 1 and 2, and that a raising stub gives an error without crashing the test
    - _Requirements: 10.4, 10.5, 10.8, 12.12_

- [ ] 9. Add the Kiro Crew app files
  - [ ] 9.1 Create `night_watch/report_agent/agent.json`
    - Use only these fields: `name` (`report_agent`), `model` (`auto`), `description`, `prompt` and `tools`
    - `prompt` holds the full text of `night_watch/report_agent/prompt.md` inline, copied exactly. `tools` allows only the MCP tool `run_night_watch` (follow the entry format in Kiro Crew's agent examples)
    - The cron entry in `app.json` must use the same `name`. No secrets, no real data and no API address
    - This replaces the earlier version, which pointed at `prompt.md` instead of holding its text
    - _Requirements: 9.3, 9.4, 9.12_

  - [ ] 9.2 Write `night_watch/app.json`
    - `night_watch/` is the app folder installed in Crew, so every path in `app.json` is relative to it
    - Use only these top-level fields: `name` `night-watch`, `version` `0.1.0`, `displayName` `Night Watch`, `description`, `author`, `license` `MIT`, `agents`, `skills`, `mcpServers`, `crons`
    - `agents`: a list with exactly one path, `report_agent/agent.json`
    - `skills`: a list with exactly one path, the folder `skills/night-watch-report`
    - `mcpServers`: `mcp.json` format with one entry that defines `command` (`python`), `args` (`["mcp_server.py"]`) and `env` (no secrets, no API address)
    - `crons`: a list with one entry holding `name`, `cron_expr` `0 2 * * *`, `message` and `agent` (`report_agent`, the name in `agent.json`)
    - Cron `message`: call `run_night_watch` exactly once. On `all_as_expected` reply with exactly one line of plain text and take no further action. On `returning_ghost` or `could_not_check` follow `night_watch/report_agent/prompt.md`
    - Must parse as valid JSON. No secrets, no real data and no hard-coded API address
    - This replaces the earlier version, which used paths from the repository root
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12_

  - [x] 9.3 Write `night_watch/skills/night-watch-report/SKILL.md`
    - Frontmatter fields: `name`, `description`, `triggers`
    - Repeat the rules: accept the checker's verdict as final, never modify files or run fixes, never state names or codes not in the summary, label results "scripted mode", never claim WCAG compliance or conformance
    - State that all example data is synthetic
    - _Requirements: 9.5, 11.8_

  - [x] 9.4 Update `night_watch/report_agent/prompt.md`
    - Call `run_night_watch` exactly once and base every statement on its summary
    - Returning ghost: at most 5 sentences, include "returning ghost", name the fixed variant, give the reason code in plain English and the report path
    - Could not check: at most 5 sentences, state the cause, name each variant, and say no verdict is available
    - If the call fails or returns nothing, report the check could not be run, with no verdict and no guessing
    - Include the verdict-is-final, no-edit, no-invention and "scripted mode" and no-WCAG-claims rules
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.9_

  - [ ]* 9.5 Write smoke tests for the app files
    - File: `night_watch/tests/test_app_files.py`
    - `app.json` parses and has only the allowed top-level fields with the required values
    - `agents` is a one-item list whose path is `report_agent/agent.json`. That file has only `name`, `model`, `description`, `prompt` and `tools`, with model `auto` and `prompt` equal to the text of `prompt.md`
    - `skills` is a one-item list whose folder holds `SKILL.md` with frontmatter `name`, `description`, `triggers`
    - `mcpServers` has one entry with `command`, `args` (`["mcp_server.py"]`) and `env`. `crons` has one entry with `name`, `cron_expr` `0 2 * * *`, `message`, `agent`, and `agent` matches the name in `agent.json`. The `message` names `run_night_watch`, the one-line reply on `all_as_expected`, and `prompt.md`
    - `app.json` and `agent.json` contain no API address and no secrets. Prompt and skill contain the required rules and the word "synthetic". Source files contain no `os.path` joins for report paths and no credentials
    - _Requirements: 1.5, 1.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 11.7, 11.8_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Run `pytest night_watch/tests` with the existing `.venv`. Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation.
- Property tests validate universal correctness properties. Unit and example tests validate specific scenarios.
- No open items. A3 is closed by a decision: the MCP server uses the official `mcp` package (FastMCP, stdio). A1, A2 and A4 are confirmed.
- A4: a broken variant returning PASSED is Could_Not_Check (exit code 2) with the explanation "Broken variant no longer blocks: the checker or test page changed". A bad `HA_API_URL` exits with code 2, prints a clear message and writes no report (Requirement 1.4).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "1.5"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.4"] },
    { "id": 3, "tasks": ["4"] },
    { "id": 4, "tasks": ["5.1", "5.2"] },
    { "id": 5, "tasks": ["5.5", "6.1"] },
    { "id": 6, "tasks": ["6.2"] },
    { "id": 7, "tasks": ["6.7"] },
    { "id": 8, "tasks": ["7"] },
    { "id": 9, "tasks": ["8.1", "9.1", "9.3", "9.4"] },
    { "id": 10, "tasks": ["8.5", "9.2"] },
    { "id": 11, "tasks": ["9.5"] },
    { "id": 12, "tasks": ["10"] }
  ]
}
```
