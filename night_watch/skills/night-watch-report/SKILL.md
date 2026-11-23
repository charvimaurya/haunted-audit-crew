---
name: night-watch-report
description: Presents the result of the nightly Night Watch check of the Send Payment journey in plain English. Reports only what the checker's summary says, in scripted mode.
triggers:
  - night watch
  - returning ghost
  - nightly check
  - run_night_watch
---

# Night Watch report skill

Use this skill when you present the result of `run_night_watch`. The broken variant of the Send Payment journey should FAIL. The fixed variant should PASS. If the fixed variant fails, that is a "returning ghost".

## Rules

1. **The checker's verdict is final.** Accept the outcome in the returned summary as it stands. Do not re-judge it, soften it or override it.
2. **Never change anything.** Do not modify files, open pull requests, push commits or run fixes. You only report.
3. **Never invent details.** Do not state any element name, selector or reason code that is not in the returned summary. If the summary does not say, say it is not available.
4. **Label every result "scripted mode".** Scripted mode follows a fixed script and uses no AI model to find issues.
5. **Never claim WCAG compliance or conformance.** A passing check means only that the scripted journey behaved as expected.

## Synthetic data

All example data in Night Watch is synthetic. No real people, accounts or payments are involved.
