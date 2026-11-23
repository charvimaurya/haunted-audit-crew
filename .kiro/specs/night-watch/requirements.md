# Requirements Document

## Introduction

Night Watch is a Kiro Crew app for Haunted Audit. Every night at 02:00 it re-runs the Send Payment journey through the Haunted Audit API, in scripted mode only. The broken variant must come back BLOCKED. The fixed variant must come back PASSED. If the fixed variant is not PASSED, Night Watch reports a "returning ghost" in plain English. Results go to dated files under `reports/`, and the process exit code tells the scheduler what happened.

This version replaces an earlier draft. These items from the earlier draft are out of scope and are not specified here: SQLite evidence log, `GET /night-watch/history` backend endpoint, Reports page or dashboard UI, `llm` mode, Docker documentation, and any change to the haunted-audit repository.

Facts taken from `docs/api-contract.md`:

- `POST /runs` with `{"variant": ..., "mode": "scripted"}` returns `202` and a `run_id`.
- `GET /runs/{run_id}` returns `status` (`running`, `complete`, `error`), `verdict` (`PASSED`, `BLOCKED`, or null) and `reason_code`.
- When `status` is `error`, the returned BLOCKED is not a real finding.
- `POST /runs` returns `429` with a `Retry-After` header (seconds) when a limit is hit. Limits: 5 runs per minute, 30 per hour, 2 at once.
- Measured on 23 Nov 2026: broken = BLOCKED (`TARGET_NOT_FOCUSABLE`), fixed = PASSED, scripted mode.

### Assumptions

A1, A2 and A4 are confirmed by the user. A3 is closed by a decision: the MCP server uses the official `mcp` Python package.

- A1 (confirmed by the user): The manifest `night_watch/app.json` uses the field names and shapes described in Requirement 9.
- A2 (confirmed by the user): The skill is a folder at `night_watch/skills/night-watch-report/` that contains `SKILL.md`.
- A3 (decision): The MCP_Server is built with the official `mcp` Python package (FastMCP, stdio transport). The package handles JSON-RPC framing, the protocol handshake and protocol errors.
- A4 (confirmed by the user): A broken variant that returns PASSED is classed as "could not check" (exit code 2) with the explanation "Broken variant no longer blocks: the checker or test page changed". It is not a returning ghost, because the scope defines a returning ghost only for the fixed variant.
- A5: Timing defaults are a poll interval of 2 seconds, a per-run timeout of 120 seconds, and at most 3 retries after a 429 response.
- A6: Exit code priority is 1, then 2, then 0.

## Glossary

- **Night_Watch**: The nightly check, made up of the Runner, the MCP_Server, the Reporter and the Crew_App.
- **Runner**: The script `night_watch/run_journeys.py` that starts runs, polls them, and decides outcomes.
- **Haunted_Audit_API**: The HTTP service that runs journeys and returns verdicts. Night Watch only reads from it and starts runs on it.
- **API_URL**: The base URL of the Haunted_Audit_API, read from the environment variable `HA_API_URL`, default `http://127.0.0.1:8000`.
- **Journey**: A named user task checked by the Haunted_Audit_API. Night Watch checks only Send Payment.
- **Variant**: Either `broken` (planted barrier present) or `fixed` (barrier removed).
- **Scripted_Mode**: The Haunted_Audit_API mode `scripted`, where a fixed script drives the journey. No AI model chooses the steps.
- **Run**: One execution of one variant, identified by a `run_id`.
- **Finished_Run**: A Run whose `status` is `complete`.
- **Errored_Run**: A Run whose `status` is `error`.
- **Verdict**: The `verdict` field of a Finished_Run, either `PASSED` or `BLOCKED`.
- **Expected_Outcome**: BLOCKED for the broken Variant, PASSED for the fixed Variant.
- **Returning_Ghost**: A Finished_Run of the fixed Variant whose Verdict is not PASSED.
- **Could_Not_Check**: A Variant for which Night_Watch has no trustworthy Verdict. Causes: Errored_Run, HTTP 429 that cannot be resolved by retrying, API unreachable, timeout, an unexpected response, or a broken Variant returning PASSED (assumption A4), which carries the explanation "Broken variant no longer blocks: the checker or test page changed".
- **Night_Report**: The pair of files `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.json`, where the date is the UTC date of the check.
- **MCP_Server**: The FastMCP stdio server `night_watch/mcp_server.py`, built on the official `mcp` Python package.
- **Crew_App**: The Kiro Crew application defined by `night_watch/app.json`.
- **Agent_File**: The JSON file `night_watch/report_agent/agent.json` that defines the Report_Agent and is listed in the `agents` field of `night_watch/app.json`.
- **Report_Agent**: The Crew_App agent defined by the Agent_File, whose instructions are in `night_watch/report_agent/prompt.md`.
- **Report_Skill**: The skill folder `night_watch/skills/night-watch-report/`, which contains a `SKILL.md` file that tells the Report_Agent how to present results.
- **Fake_API**: An in-process test double for the Haunted_Audit_API. It opens no network connection.

## Requirements

### Requirement 1: Read configuration

**User Story:** As a maintainer, I want the API address to come from the environment, so that Night Watch runs on any machine without code changes.

#### Acceptance Criteria

1. WHEN the Runner starts, THE Runner SHALL read the API_URL from the environment variable `HA_API_URL`.
2. IF `HA_API_URL` is not set, is an empty string, or contains only whitespace characters, THEN THE Runner SHALL use `http://127.0.0.1:8000` as the API_URL.
3. WHEN the API_URL has one or more trailing slashes after leading and trailing whitespace is removed, THE Runner SHALL remove all trailing slashes and the surrounding whitespace before building request URLs, so that no request URL contains a double slash after the host.
4. IF the API_URL does not begin with `http://` or `https://`, THEN THE Runner SHALL stop before sending any request, SHALL exit with exit code 2, and SHALL print a plain-English error message that names `HA_API_URL` as invalid and states that it must begin with `http://` or `https://`.
5. THE Runner SHALL contain no credentials, tokens, or real user data in its source files, default values, or output.
6. THE Runner SHALL build file paths with `pathlib` so that the same code runs on Windows and Linux without changes.

### Requirement 2: Run the two scripted variants

**User Story:** As a maintainer, I want the broken and fixed Send Payment variants run each night, so that I can see whether the planted barrier and its fix still behave as expected.

#### Acceptance Criteria

1. WHEN the Runner is started, THE Runner SHALL send `POST /runs` with the body `{"variant": "broken", "mode": "scripted"}` and then `POST /runs` with the body `{"variant": "fixed", "mode": "scripted"}`, in that order.
2. THE Runner SHALL send only the fields `variant` and `mode` in each `POST /runs` body.
3. THE Runner SHALL send the second `POST /runs` only after the first Run has reached the status `complete` or `error`, or has been classified as Could_Not_Check, so that at most one Run is in progress at any time.
4. WHEN the `POST /runs` response status is `202`, THE Runner SHALL read `run_id` from the response and poll `GET /runs/{run_id}`.
5. WHILE the `status` field of a Run is neither `complete` nor `error`, THE Runner SHALL poll `GET /runs/{run_id}` every 2 seconds (plus or minus 0.5 seconds), and SHALL stop polling that Run as soon as `status` is `complete` or `error`.
6. WHEN the broken Run has reached the status `complete` or `error`, or has been classified as Could_Not_Check, THE Runner SHALL start the fixed Run.
7. IF a `POST /runs` request returns a status other than `202`, returns a `202` response without a `run_id`, or fails to connect or to receive a response within 10 seconds, THEN THE Runner SHALL classify that Variant as Could_Not_Check with a plain-English reason, SHALL NOT poll for that Variant, and SHALL continue with the next step (starting the fixed Run if the broken Variant was affected), except where Requirement 5 or Requirement 6 says otherwise.
8. IF a Run's `status` is not `complete` or `error` within 120 seconds of its `POST /runs` being accepted, or a `GET /runs/{run_id}` poll fails 3 times in a row, THEN THE Runner SHALL stop polling that Run, SHALL classify that Variant as Could_Not_Check with a plain-English reason, and SHALL keep the results already collected for the other Variant.

### Requirement 3: Check status before trusting the verdict

**User Story:** As a maintainer, I want a crashed run never to be read as a real finding, so that reports contain only trustworthy verdicts.

#### Acceptance Criteria

1. WHILE the `status` of a Run is `running`, THE Runner SHALL ignore the `verdict` field of that Run and SHALL NOT record a Verdict for the Variant until `status` changes.
2. WHEN the `status` of a Run is `error`, THE Runner SHALL classify that Variant as Could_Not_Check, SHALL ignore the `verdict` field, and SHALL include the Variant name and the `status` value in the Could_Not_Check entry.
3. WHEN the `status` of a Run is `complete` and `verdict` is exactly `PASSED` or exactly `BLOCKED` (case-sensitive), THE Runner SHALL record that Verdict, unchanged, for the Variant.
4. IF the `status` of a Run is `complete` and `verdict` is absent, null, an empty string, or any value other than exactly `PASSED` or `BLOCKED`, THEN THE Runner SHALL classify that Variant as Could_Not_Check, SHALL NOT record a Verdict, and SHALL include the Variant name and the received `verdict` value in the Could_Not_Check entry.
5. IF the `status` of a Run is absent, null, or any value other than exactly `running`, `complete` or `error`, THEN THE Runner SHALL classify that Variant as Could_Not_Check, SHALL ignore the `verdict` field, and SHALL include the Variant name and the received `status` value in the Could_Not_Check entry.
6. THE Runner SHALL take every Verdict and `reason_code` from the Haunted_Audit_API response and SHALL NOT compute or alter either value.
7. IF a Variant is classified as Could_Not_Check, THEN THE Runner SHALL continue checking the remaining Variants and SHALL NOT report that Variant as a "returning ghost" or as a passing or failing result.

### Requirement 4: Judge each variant against its expected outcome

**User Story:** As a maintainer, I want the fixed variant failing to be called a returning ghost, so that a regression is obvious.

#### Acceptance Criteria

1. WHEN the broken Variant has a Finished_Run with Verdict BLOCKED, THE Runner SHALL mark the broken Variant as "as expected".
2. WHEN the fixed Variant has a Finished_Run with Verdict PASSED, THE Runner SHALL mark the fixed Variant as "as expected".
3. WHEN the fixed Variant has a Finished_Run with Verdict BLOCKED, THE Runner SHALL mark the fixed Variant as a Returning_Ghost and SHALL record the `reason_code` from the response exactly as received, or record "no reason given" if the response has no `reason_code` or its value is empty.
4. WHEN the broken Variant has a Finished_Run with Verdict PASSED, THE Runner SHALL classify the broken Variant as Could_Not_Check with the explanation exactly "Broken variant no longer blocks: the checker or test page changed", SHALL NOT mark it as a Returning_Ghost, and the invocation SHALL end with exit code 2 unless a Returning_Ghost exists (assumption A4).
5. IF a Finished_Run has a Verdict other than BLOCKED or PASSED, THEN THE Runner SHALL classify that Variant as Could_Not_Check, with an explanation naming the unrecognised Verdict value, and SHALL NOT mark it as "as expected" or as a Returning_Ghost.
6. WHEN both Variants have been judged, THE Runner SHALL keep each Variant's judgement independent, so that a Could_Not_Check result for one Variant does not change the judgement of the other Variant.

### Requirement 5: Handle rate limits

**User Story:** As a maintainer, I want Night Watch to stay inside the API limits, so that it never gets blocked or blocks other users.

#### Acceptance Criteria

1. WHEN `POST /runs` returns HTTP 429 and the `Retry-After` header is a whole number of seconds from 0 to 120, THE Runner SHALL wait that many seconds and then repeat the same `POST /runs` for the same Variant.
2. IF `POST /runs` returns HTTP 429 for the 4th time for the same Variant in one invocation, THEN THE Runner SHALL stop retrying that Variant, classify it as Could_Not_Check, and record in the Night_Report that the rate-limit retry limit of 3 retries was reached.
3. IF `POST /runs` returns HTTP 429 and the `Retry-After` header is missing, is not a whole number, is negative, or is greater than 120, THEN THE Runner SHALL NOT wait or retry, SHALL classify that Variant as Could_Not_Check, and SHALL record in the Night_Report that the `Retry-After` value was unusable.
4. THE Runner SHALL start no more than 2 Runs in one invocation, which is below the limits of 5 Runs per minute, 30 Runs per hour and 2 concurrent Runs.
5. WHEN the Runner waits for a `Retry-After` delay, THE Runner SHALL record in the Night_Report the Variant, the wait length in seconds, and the retry number (1 to 3).
6. IF a Variant is classified as Could_Not_Check because of rate limiting, THEN THE Runner SHALL still attempt the other Variant and SHALL NOT report a returning ghost for the affected Variant.

### Requirement 6: Handle API failures and timeouts

**User Story:** As a maintainer, I want an unreachable or slow API to be reported as "could not check", so that an outage is never mistaken for a pass or a returning ghost.

#### Acceptance Criteria

1. IF the Haunted_Audit_API refuses the connection, does not resolve, or does not answer an HTTP request within 10 seconds, THEN THE Runner SHALL classify the Variant being checked and every Variant not yet checked as Could_Not_Check, SHALL NOT send further requests to the Haunted_Audit_API in that invocation, and SHALL keep the classifications of Variants already checked unchanged.
2. IF a Run is not a Finished_Run or Errored_Run within 120 seconds of its `POST /runs` response, THEN THE Runner SHALL stop polling that Run, classify that Variant as Could_Not_Check with the explanation "timed out", and continue to check the next Variant not yet checked.
3. IF `POST /runs` or `GET /runs/{run_id}` returns an HTTP status of 400 or above other than 429, THEN THE Runner SHALL classify that Variant as Could_Not_Check, record the HTTP status code in the explanation, and continue to check the next Variant not yet checked.
4. IF a response body is not valid JSON or lacks a required field, THEN THE Runner SHALL classify that Variant as Could_Not_Check, record an explanation naming the invalid body or the missing field, and continue to check the next Variant not yet checked.
5. IF the Haunted_Audit_API is unreachable while the broken Variant is being started, THEN THE Runner SHALL write a Night_Report that lists both Variants as Could_Not_Check, SHALL NOT report a returning ghost, and SHALL NOT report either Variant as passed.
6. IF the Runner classifies any Variant as Could_Not_Check and no Returning_Ghost exists, THEN THE Runner SHALL end the invocation with exit code 2 after the Night_Report is written.

### Requirement 7: Exit codes

**User Story:** As a scheduler, I want a distinct exit code for each outcome, so that I can react without parsing the report.

#### Acceptance Criteria

1. WHEN the check completes and both Variants are "as expected" (the broken Variant is BLOCKED and the fixed Variant is PASSED), THE Runner SHALL exit with code 0.
2. WHEN the check completes and at least one Returning_Ghost exists, THE Runner SHALL exit with code 1, even if the other Variant is Could_Not_Check.
3. WHEN the check completes, no Returning_Ghost exists, and at least one Variant is Could_Not_Check, THE Runner SHALL exit with code 2.
4. IF an unexpected exception occurs after the check has started, THEN THE Runner SHALL write a Night_Report that states the exception type and a plain-English description of the failure, SHALL exit with code 2, and SHALL NOT exit with code 0 or 1.
5. IF the Night_Report cannot be written while the Runner is handling an unexpected exception, THEN THE Runner SHALL still exit with code 2 and SHALL print the exception type to standard error.
6. THE Runner SHALL exit with exactly one code from the set {0, 1, 2} on every run that reaches the end of the check, and SHALL exit within 5 seconds after the last Variant result is determined.

### Requirement 8: Write the Night_Report

**User Story:** As a maintainer, I want a plain-English report and a machine-readable copy for every night, so that I can read the result and other tools can parse it.

#### Acceptance Criteria

1. WHEN a check ends, THE Runner SHALL write `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.json`, where YYYY-MM-DD is the UTC date of the `checked_at` timestamp.
2. IF the `reports` directory does not exist, THEN THE Runner SHALL create it before writing either file.
3. IF the `reports` directory cannot be created or either file cannot be written, THEN THE Runner SHALL print to standard error one line that names the path and states the cause in plain English, and SHALL exit with code 2.
4. WHEN a Night_Report for the same date already exists, THE Runner SHALL overwrite both files with the latest result, so that after the write neither file contains content from the earlier check.
5. THE Runner SHALL write a JSON file that contains exactly these fields: `checked_at` (UTC ISO-8601 timestamp ending in `Z`), `api_url` (the value of HA_API_URL or the default), `mode` (the value `scripted`), `journey` (the value `send-payment`), `outcome` (one of `all_as_expected`, `returning_ghost`, `could_not_check`), `exit_code` (integer equal to the exit code of the Runner process), and `variants`.
6. THE Runner SHALL write in `variants` exactly two entries, one for `broken` and one for `fixed`, each with the fields `variant`, `expected_verdict` (`BLOCKED` for `broken`, `PASSED` for `fixed`), `run_id` (string or null), `status` (string or null), `verdict` (string or null), `reason_code` (string or null), `result` (one of `as_expected`, `returning_ghost`, `could_not_check`), and `explanation` (plain English, 1 to 500 characters).
7. WHEN a Returning_Ghost exists, THE Runner SHALL write in the Markdown file at least one sentence that contains the words "returning ghost", names the `fixed` variant, and states the `reason_code` value together with a plain-English description of it.
8. WHEN a Variant is Could_Not_Check, THE Runner SHALL write in the Markdown file the name of that Variant and its cause in plain English, and SHALL set that entry's `result` to `could_not_check`.
9. THE Runner SHALL include the words "scripted mode" in the Markdown file and SHALL set the JSON `mode` field to `scripted`, and SHALL state in the Markdown file that scripted mode follows a fixed script and does not use an AI model to drive the journey.
10. THE Runner SHALL NOT write the text "WCAG" together with the words "compliant", "compliance", "conformant", or "conformance" in any Night_Report.
11. WHEN both report files have been written, THE Runner SHALL print to standard output exactly one summary line that contains the `outcome` value and the path of the Markdown file.
12. FOR ALL valid result sets, writing the JSON file and then reading it back SHALL produce a result set equal to the original (round-trip property), including null values and non-ASCII characters in `explanation`.

### Requirement 9: Register the app with Kiro Crew

**User Story:** As a maintainer, I want the app described in one manifest, so that Kiro Crew can schedule it each night.

#### Acceptance Criteria

1. THE Crew_App SHALL define in `night_watch/app.json` the fields `name` with the value `night-watch`, `displayName` with the value `Night Watch`, `version` with the value `0.1.0`, `license` with the value `MIT`, `description`, and `author`.
2. THE `night_watch/app.json` file SHALL contain only these top-level fields: `name`, `version`, `displayName`, `description`, `author`, `license`, `agents`, `skills`, `mcpServers` and `crons`.
3. THE `agents` field SHALL be a list with exactly one path, which points to the Agent_File, with the path resolved relative to the `night_watch/` folder (the app folder installed in Crew), so the path is `report_agent/agent.json`.
4. THE Agent_File SHALL contain only the fields `name`, `model`, `description`, `prompt` and `tools`, SHALL set `model` to `auto`, and SHALL hold the full text of `night_watch/report_agent/prompt.md` inline in `prompt`.
5. THE `skills` field SHALL be a list with exactly one path, which points to the Report_Skill folder (`skills/night-watch-report`, relative to the `night_watch/` folder), and that folder SHALL contain a `SKILL.md` file whose frontmatter has the fields `name`, `description` and `triggers`.
6. THE `mcpServers` field SHALL have the same format as `mcp.json`, with exactly one entry that starts the MCP_Server and defines `command`, `args` and `env`, with `args` set to `mcp_server.py`, relative to the `night_watch/` folder.
7. THE `crons` field SHALL be a list with exactly one entry that has the fields `name`, `cron_expr`, `message` and `agent`, where `cron_expr` is `0 2 * * *` (02:00 every day) and `agent` refers to the Report_Agent.
8. THE `message` of the cron entry SHALL instruct the Report_Agent to call the `run_night_watch` tool exactly once per scheduled run.
9. WHEN the `run_night_watch` tool returns the outcome `all_as_expected`, THE `message` of the cron entry SHALL instruct the Report_Agent to reply with exactly one line of plain text and to take no further action.
10. WHEN the `run_night_watch` tool returns the outcome `returning_ghost` or `could_not_check`, THE `message` of the cron entry SHALL instruct the Report_Agent to follow `night_watch/report_agent/prompt.md`.
11. THE `night_watch/app.json` file SHALL parse as valid JSON with no syntax errors.
12. THE `night_watch/app.json` file and the Agent_File SHALL contain no secrets, no credentials, no real data, and no hard-coded API address, so that the API address is read only from the `HA_API_URL` environment variable.

### Requirement 10: Expose the check through an MCP server

**User Story:** As the Crew agent, I want one tool that runs the check, so that I can trigger it and read the summary.

#### Acceptance Criteria

1. THE MCP_Server SHALL be built with the official `mcp` Python package (FastMCP) and SHALL use the stdio transport, leaving JSON-RPC framing and protocol handling to the package (assumption A3).
2. THE MCP_Server SHALL be named `night-watch` and SHALL answer the `initialize` handshake through the `mcp` package, with no hand-written protocol code.
3. THE MCP_Server SHALL register exactly one tool named `run_night_watch`, and that tool SHALL take no arguments.
4. WHEN the `run_night_watch` tool is called, THE MCP_Server SHALL run the Runner exactly once and return a text summary containing the `outcome`, the `exit_code`, the plain-English explanation for each Variant (broken and fixed), and the path of the Night_Report.
5. IF the Runner ends with exit code 1 or 2, THEN THE MCP_Server SHALL return the summary as a normal tool result without an error, and SHALL keep the server process running to accept the next request.
6. IF a `tools/call` request names a tool other than `run_night_watch`, THEN THE `mcp` package SHALL reject it with a protocol error, and the Runner SHALL NOT run.
7. IF the MCP_Server receives input that is not valid JSON, THEN THE `mcp` package SHALL answer with a parse error, and THE MCP_Server SHALL keep running.
8. IF the Runner raises an unexpected exception while `run_night_watch` runs, THEN THE MCP_Server SHALL return an error result for that call, and SHALL keep running to accept the next request.
9. THE MCP_Server SHALL write only JSON-RPC protocol messages to standard output and SHALL write all diagnostic text to standard error.

### Requirement 11: Instruct the report agent

**User Story:** As a maintainer, I want a short plain-English message when something is wrong, so that I can act on it without reading JSON.

#### Acceptance Criteria

1. THE Report_Agent prompt in `night_watch/report_agent/prompt.md` SHALL instruct the agent to call `run_night_watch` exactly once per nightly run and to base every statement in its message on the summary returned by that call.
2. WHEN the outcome is `returning_ghost`, THE Report_Agent prompt SHALL instruct the agent to write a summary of at most 5 sentences that names the fixed variant, includes the exact words "returning ghost", states the `reason_code` from the summary as a plain-English sentence, and gives the path of the Night_Report file.
3. WHEN the outcome is `could_not_check`, THE Report_Agent prompt SHALL instruct the agent to write a summary of at most 5 sentences that states the cause given in the summary, names each affected Variant, and states that no Verdict is available for each named Variant.
4. THE Report_Agent prompt SHALL instruct the agent to accept the checker's Verdict as final and never to re-evaluate, override or reinterpret it.
5. THE Report_Agent prompt SHALL instruct the agent never to modify source files, open pull requests, push commits or run fix tools.
6. THE Report_Agent prompt SHALL instruct the agent never to state an element name, selector or reason code that does not appear in the returned summary.
7. THE Report_Agent prompt SHALL instruct the agent to label every result as "scripted mode" and never to claim WCAG compliance or conformance.
8. THE `SKILL.md` file of the Report_Skill SHALL repeat the rules in criteria 4 to 7 and SHALL state that all example data is synthetic.
9. IF the call to `run_night_watch` fails or returns no summary, THEN THE Report_Agent prompt SHALL instruct the agent to report that the check could not be run, to state that no Verdict is available, and not to guess an outcome.

### Requirement 12: Test against a fake API

**User Story:** As a maintainer, I want fast tests that need no network, so that I can trust changes to the Runner.

#### Acceptance Criteria

1. THE test suite in `night_watch/tests/test_run_journeys.py` SHALL use pytest and Hypothesis.
2. THE test suite SHALL replace all HTTP calls with the Fake_API and SHALL open no network connection, so that every test passes with the host network disabled.
3. THE test suite SHALL replace sleeping with a recorded fake clock that logs each requested sleep duration in seconds, so that no test waits in real time and each test completes in under 5 seconds of real time.
4. WHEN the Fake_API returns a Verdict of BLOCKED for the broken Variant and PASSED for the fixed Variant, THE test suite SHALL assert that the Runner exits with code 0.
5. WHEN the Fake_API returns a Verdict of BLOCKED for the fixed Variant, THE test suite SHALL assert that the Runner exits with code 1 and that the Night_Report Markdown file contains the words "returning ghost".
6. IF the Fake_API refuses connections, THEN THE test suite SHALL assert that the Runner exits with code 2 and that both Night_Report files (Markdown and JSON) exist after the Runner exits.
7. IF a Run stays in `running` status for more than 120 seconds of fake clock time, THEN THE test suite SHALL assert that the Runner exits with code 2 and that the fake clock records no more than 120 seconds of total waiting for that Run before the Runner gives up.
8. WHEN `POST /runs` returns 429 with a `Retry-After` header of N seconds (N between 1 and 60), THE test suite SHALL assert that the fake clock recorded a sleep of exactly N seconds before the next `POST /runs` request, and that the Runner then completes with the second response.
9. IF a Run has `status` `error` and `verdict` BLOCKED, THEN THE test suite SHALL assert that the Runner ignores the verdict and exits with code 2.
10. THE test suite SHALL include a Hypothesis property that, FOR ALL combinations of `status`, `verdict` and Variant, a fixed Variant with a Verdict of BLOCKED is a returning ghost (exit code 1), and a fixed Variant with `status` error, HTTP 429, timeout, a null Verdict or any other Verdict is could not check (exit code 2).
11. THE test suite SHALL include a Hypothesis property that, FOR ALL valid result sets, the JSON round-trip in Requirement 8 holds.
12. THE test suite SHALL include a small test that calls the `run_night_watch` tool function directly with a runner stub, and asserts the summary text for exit codes 0, 1 and 2, and that a raising stub is reported as an error.
13. THE test suite SHALL pass when run with the existing `.venv` and the command `pytest night_watch/tests` on both Windows and Linux.
14. THE test suite SHALL use only synthetic data, with no real credentials, real URLs, or real user records in test code or fixtures.