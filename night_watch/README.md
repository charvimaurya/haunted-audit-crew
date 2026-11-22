# Night Watch

Night Watch runs scheduled accessibility journey checks for Haunted Audit.

- `app.json` holds the nightly schedule configuration.
- `run_journeys.py` will run the journey checks.
- `report_agent/prompt.md` will define how to summarize regressions.
- `tests/test_run_journeys.py` will cover the journey runner.

The history API and Reports UI live in the main Haunted Audit repository.
