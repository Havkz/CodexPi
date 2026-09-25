# Usage / Limits history

The 2026-09-24 clarification is appended to `C:\CODEXPI_GOAL.md`, lines
2959–2975, and represented in the requirement audit. No reference images were
available or used. This does not replace the lifecycle requirements.

## Data and boundaries

The controller's existing read-only `account/rateLimits/read` call supplies
observations. `usedPercent` becomes `100 - usedPercent`; duration identifies
the 300/1440-minute daily window and 10080-minute weekly window. Missing,
invalid or unknown windows are not treated as fully available. Account data
never changes native goal state, queue admission or automatic-resume authority.
The [official app-server documentation](https://learn.chatgpt.com/docs/app-server)
describes the account rate-limit interface; the installed Pi bridge was also
read directly on September 24 (300 and 10080 minutes).

SQLite schema v3 adds `usage_samples`. Each series stores at most one actual
observation per 60 seconds, for eight days, with an additional 12,000-row ceiling
per series. Samples and the latest account snapshot commit atomically. Existing
SQLite backup/restore includes the table. Clock rollback cannot rewrite samples.
No historic values are backfilled from the current balance; collection starts
with the first successful poll after installation.

The authenticated, no-store `/api/usage` endpoint returns the last 24 hours for
Daily/5h and seven days for Weekly. Five-minute / one-hour buckets retain their
actual first, minimum, maximum and last observations, including their original
timestamps. A gap over three minutes or a changed window duration splits the
line before reduction. No averages or synthetic samples are stored or returned.
Sub-minute changes between observations cannot be reconstructed. The chart
explicitly describes connecting lines and reduction, not continuous measurement.

There is no assumption of 100% after an advertised reset time. A refill appears
only when a later real observation increases the remaining percentage. Missing
or stale observations and failed requests remain labelled. Project usage-limit
and budget-limit messages are preserved separately below the new cards.

## Presentation

Weekly is the initial view; the toggle switches independent measured series.
A code-native SVG uses a fixed 0–100% vertical scale, a thin round-joined line,
10% opacity area fill and subtle time/grid markers. Only actual observations
anchor the line; no spline overshoot. New plot data fades in over 450ms, and bar
width changes use CSS transitions. Reduced-motion preferences disable both.
Two native horizontal progress elements show remaining percentages, daily in
the existing cyan token and weekly in purple, with exact reset times and
coarse remaining time. Cards, fonts, borders and spacing reuse dashboard tokens.

## Verification as of 2026-09-25

- `tests/test_usage.py`: v2 migration, percent direction, invalid/missing values,
  real-only reduction, outage separation, sampling cadence, clock rollback,
  passed reset without fabricated refill, database reopen, backup, retention,
  hard row ceiling and bounded reduced payload.
- `tests/test_web.py`: endpoint requires authentication and inherits no-store;
  correct current/historical values. Existing Host/Origin/CSRF/login tests remain.
- `tests/test_scheduler.py`: actual controller polling method stores account
  telemetry and preserves it on provider failure, without resuming projects,
  inventing native usage-limited states or emitting notifications.
- `py -3.11 Setup/verify-usage-ui.py`: isolated Edge with synthetic, explicitly
  test-only API responses; independent views, weekly default, 0%/100% bars,
  reset waiting, gaps, animation/reduced motion, unknown/stale states, reload,
  1440px desktop and 390/320px mobile. No page errors or CSP violations.
  Screenshots in ignored `state/usage-fixture-*.png` were visually inspected.
- **Pi installation and real-history/controller-restart verification pending.**
  On September 25 SSH and dashboard TCP connections to 192.168.2.105 failed
  before authentication. No deployment or Pi mutation occurred for this change.
  `Setup/verify-usage-ui.py --live` is the ready read-only dashboard verifier.
  A real captured refill remains unobserved; synthetic chart coverage is not
  represented as live quota/reset evidence.

Before deploying, recheck no native goal is executing and back up SQLite v2.
Deploy all updated Python and web assets together, then restart only the idle
controller. Verify real samples, mapped native statuses, a second idle restart
and retained observations, then run the live browser verifier and Pi tests.
