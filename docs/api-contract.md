## API contract for Night Watch

Source: `data-contract.md` and `agent/api/main.py`, `agent/api/limits.py` in the haunted-audit repo (read only).

**Start command (Windows)**, run from the haunted-audit folder:

```
.venv\Scripts\activate
python -m uvicorn agent.api.main:app --host 127.0.0.1 --port 8000
```

**Base URL:** `http://127.0.0.1:8000` (Night Watch reads it from `HA_API_URL`).

**Start a run: `POST /runs`** (returns `202 {"run_id": "<id>", "status": "running"}`)

Broken variant, scripted mode:

```json
{"variant": "broken", "mode": "scripted"}
```

Fixed variant, scripted mode:

```json
{"variant": "fixed", "mode": "scripted"}
```

Unknown fields are rejected with `422`. Optional fields: `max_steps` (1 to 80, default 25) and `timeout_seconds` (0 to 300, default 90). Night Watch sends only `variant` and `mode`.

**Read a run: `GET /runs/{run_id}`** (`404 {"detail": "run not found"}` for an unknown id)

| Field | Values |
|---|---|
| `verdict` | `"PASSED"`, `"BLOCKED"`, or `null` while the run is still going |
| `reason_code` | `"TARGET_NOT_FOCUSABLE"`, `"FOCUS_TRAP"`, `"NO_ACTIVATION"`, `"STEP_LIMIT"`, `"TIMEOUT"`, or `null` (null when `PASSED`) |
| `status` | `"running"`, `"complete"`, `"error"` |

**How to tell a run is finished:** poll `GET /runs/{run_id}` until `status` is `"complete"` or `"error"`. While `status` is `"running"`, `verdict` and `result` are `null`. If `status` is `"error"`, the run crashed. `result` then holds only `run_id`, `error` and `verdict: "BLOCKED"`, so do not treat that BLOCKED as a real finding.

**Rate limit:** `POST /runs` returns `429` with a `Retry-After` header (seconds) and `{"detail": "<plain sentence>"}`. Defaults are 5 runs per minute and 30 per hour per client IP, and 2 runs at once. Night Watch needs two runs a night, so wait for `Retry-After` and retry.

Measured 23 Nov 2026 on Shilpa's laptop: broken = BLOCKED (TARGET_NOT_FOCUSABLE), fixed = PASSED, scripted mode.
