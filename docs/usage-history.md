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
- **Pi installation and real-history/controller-restart verification passed.**
  A temporary Windows VPN LAN block was resolved by the user. Before deployment,
  all native goals were confirmed inactive and SQLite v2 was backed up to
  `backups/sqlite/codexpi-20260925-145048-1790340648086670670.db`; code backup is
  `backups/code/before-usage-20260925-1451.tgz`. Only the idle controller restarted.
  Schema v3 and actual account observations were confirmed: first sample at
  `1790340698.5807304`, Daily/5h 18% and Weekly 25% remaining. A second restart
  retained both exact rows; the next account poll was confirmed at
  `1790340754.1151428`. Project IDs/statuses stayed unchanged, no native goal ran.
  `Setup/verify-usage-ui.py --live` passed at 1440/390/320px with real data,
  weekly default, independent series, no page errors or CSP violations.
  Screenshots `state/usage-live-*.png` were visually inspected. The Pi suite ran
  43 tests successfully (one expected Windows-only DPAPI skip).
- A genuine Daily/5h refill was subsequently captured on September 25: the
  observation at `1790357266.0241644` had 0% remaining and advertised reset
  `1790357280`; the observation at `1790357328.8293986` had 100% remaining.
  Later real observations showed consumption again (94% at `1790357836.9241934`).
  Both endpoints remain in the reduced history and the actual Daily chart.
  This proves account-history refill capture, **not** automatic Unsnooze goal
  resume: the user's project stayed blocked awaiting their decision throughout.
  At first installation the honest display was one observed point, not a
  fabricated historical week.

The first CI run `36136193345` exposed a cold-boot timing defect on Linux:
`last_unsnooze_poll=0` was treated as a previous poll, so an uptime under 60
seconds suppressed the initial account/Unsnooze read. The same failure was
reproduced locally at a deterministic monotonic clock of five seconds. The
shared polling condition now throttles only after a previous poll exists.
The regression also proves a second immediate call is still throttled and
provider failure retains history without changing goal state. Local and Pi
43-test suites passed after the fix; the source CI rerun is recorded separately.

For future deployments, recheck no native goal is executing, back up SQLite,
deploy Python and web assets together, and restart only the idle controller.

## Existing-logo favicon

The September 25 favicon addition uses the existing `brand-mark` HTML/CSS,
rendered by `Setup/build-favicon.py` at 16/32/48px and wrapped in a standard ICO
container. The attached user example was not copied. No image or chart runtime
dependency was added. Both login and dashboard reference `/favicon.ico`.
`tests/test_web.py` validates unauthenticated LAN delivery and all embedded PNG
sizes. Live Pi delivery returned HTTP 200 with `image/vnd.microsoft.icon`; an
isolated browser decoded the actual resource successfully. `--live` verifies
both pages and byte-for-byte equality with the deployed asset. The 48px generated
preview was visually inspected and matches the existing dark C/chevron mark.
