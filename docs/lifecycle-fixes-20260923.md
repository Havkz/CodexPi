# Lifecycle repair evidence, 2026-09-23

This is incremental evidence, not final acceptance of the full CodexPi goal.
The source specification now has 2,957 lines. Its original 2,900 lines were
preserved; appended lifecycle, migration and verification requirements are
included in the lossless audit. No new root goal was created.

## Reproduction and exact causes

- UserTestProject had no native goal in `thread/goal/get`, the native goal DB,
  or its rollout. It was idle in its exact mapped tmux pane. Its DB nevertheless
  retained a resume operation from September 21. Run now and Resume both used
  the same preempting method and unconditionally sent `/goal resume`, which
  cannot resume a nonexistent goal. The TUI showed repeated goal-set failures.
- After 30 seconds, `resume_ready` raised on every scheduler iteration. This
  appeared under Raspberry Pi infrastructure even though the Pi was online,
  and prevented later Unsnooze and Discord processing in that iteration.
- Both the frontend and lifecycle backend rejected deletion whenever any
  operation existed, including this permanently pending resume.
- Recovery copied native limited status into SQLite without its notification;
  normal polling wrote status and outbox separately. A restart/crash could
  therefore lose the transition notification. Regression tests failed before
  repair. This does NOT establish that a real mapped goal hit a provider limit:
  the user clarified that the actual exhausted limit was in another CLI session.
- The admission gate rejected every config batch, including the exact native
  0.155.1 model-selection pair. No arbitrary config exception was needed.
- During live restart testing an interactive Codex update dialog prevented TUI
  startup. Managed launches now disable that startup prompt only; Codex was not
  upgraded. Session readiness is checked, not assumed from pane existence.

## Changes

Resume and queue promotion are separate actions. Ordinary Resume never preempts
another selected project; Run now is offered only for meaningful promotion.
Each resume has a durable ID, a bounded result, native session/cwd verification,
and either confirmed native execution or a clearly labeled restored empty
session. Sending a slash is journaled before delivery and never blindly repeated
after a crash. A failed action is project-specific, not Pi-offline status.
The dashboard keeps its loading indicator beyond HTTP acknowledgement, polls
while waiting, prevents duplicate clicks, and displays the final native result.
Details no longer contains its own Details button. Open details stay current.

Native status and transition notification are now committed atomically, also
during recovery. Account quota metadata never invents a goal or goal status.
Known reset data survives restart; late reset data edits the existing Discord
message rather than sending another notification. Deduplication is no longer
limited to the last 50 messages. Discord delivery is independent of unrelated
scheduler failures. Unsnooze still uses its existing detector and reset records;
automatic wakes also reject user-decision blockers.

Delete can supersede only resume operations, not another lifecycle operation.
It journals deletion before quiescence, refreshes Unsnooze cancellation after
the pane exits, and keeps the existing archive, ownership, GitHub retention,
channel removal, backup, and transactional mapping cleanup. Queue positions are
compacted after completion/deletion and reconciled during recovery.

Only `config/batchWrite` with exactly `model` and `model_reasoning_effort`, scalar
validated values, replace semantics, and the default user config is admitted
from a mapped ready TUI. Other keys, mixed batches, file targets, profiles,
parent tables, merge operations, and `config/value/write` remain denied.

## Verified live

- `Setup/verify-lifecycle-fixes.py`: UserTestProject session
  `01a0c422-77b7-7c63-80df-26f370c98a7b` restored without inventing a goal;
  result `96aed0e8-50d8-4a14-be0a-d0ac737ea2b6` was confirmed by the native
  session identity and cwd. Delete enabled; no Run now on queue head; no nested
  Details. Delayed HTTP/native acknowledgement and error presentation were
  separately exercised with explicitly synthetic browser fixtures.
- Live `/model`: changed gpt-6-astra to gpt-6-sol in that mapped TUI and restored
  **gpt-6-astra medium**; native config persistence and the rendered TUI agree.
- `/usr/bin/bwrap` 0.11.0 was already installed and on the native service PATH.
  The bridge process predated installation. After its idle-state-checked restart
  the old startup warning disappeared. `Setup/verify-sandbox.py` proves user
  namespaces work, Codex workspace writes succeed, and outside writes fail with
  a read-only filesystem. AppArmor user-namespace restriction remains `1`.
- `Setup/verify-delete-resume.py`: project
  `1afa73bd-fd5a-4be7-bd81-0bbac19dc556`, session
  `01a0cf5d-ae6b-76a3-a66e-c657e21def92`, was deleted through the real dashboard
  while paused with a queued resume. Session archive, missing tmux/DB mapping,
  Discord 404, recovery backup, and preserved private GitHub repo independently
  checked. No user project was deleted.
- `Setup/verify-native-resume.py`: dedicated project
  `0aeed393-d293-4730-9427-fa696067e55c`, session
  `01a0cf5f-9042-7da3-b8e2-5b5deb0b62cd`, accepted its test goal through the
  mapped TUI. Run now led to actual native execution and dashboard active state,
  then completed with pushed SHA `da101cb470ae8e6253ef3faded47e43a5e988236`.
- `Setup/verify-design.py`: live login/dashboard/details at 1920, 1440, 375 and
  430 pixels, no overflow or browser errors. Queue/reorder/pause/resume controls
  additionally exercised through synthetic mutation fixtures.

## Verification boundaries and remaining work

27 unit tests pass on Windows. The final Pi rerun passed 26 tests with one
Windows-only DPAPI skip. All four GitHub Actions jobs (Windows/Ubuntu,
Python 3.11/3.13) passed for code commit
`a524d293155cff2930f3fb1115afce9c029d3455`:
https://github.com/Havkz/CodexPi/actions/runs/35898363930

A current genuine mapped provider-limit -> reset -> Unsnooze -> native resume
cycle has NOT yet been observed. Native limit states, outbox/crash handling,
reset persistence, and blocked wake/delete variants have automated evidence,
not a fabricated live usageLimited result. The real provider limit originally
reported was outside UserTestProject. Live account metadata was available during
testing. Full end-to-end limit/reset proof remains pending.

Migration of Windows session `01a072f0-df80-7152-aff3-a5e66960c071` has NOT started.
Its reusable migration mechanism and execution remain required, strictly after
the other requirements are verified. The broader original goal and complete
requirement-by-requirement final audit remain unfinished.

## Completion gate follow-up

The final requirement review reproduced six CI-gate failures before repair:
missing runs with committed workflows were accepted as unconfigured, partial
workflow coverage and wrong-commit results could pass, empty conclusions could
pass, a failed old attempt masked its successful retry, and failed final CI
left the project active while repeatedly emitting a critical event.

The gate now enumerates workflow files from the exact Git commit and paginates
GitHub's workflow-run API. Only matching SHA results count; the latest run and
attempt per workflow/event supersede older results. A manual-dispatch success
does not hide a push failure. Final failure blocks the native goal and records
one stalled transition without advancing the queue. CI-state changes and their
notification are committed together.

Conservative boundary: a committed workflow with no run remains pending,
including disabled, manual-only and path-filtered workflows. CodexPi does not
infer that a missing check succeeded or provide a completion bypass. The project
must arrange the relevant workflow execution or correct its CI configuration.

Verification on 2026-09-23: 29 Windows tests passed; Pi Python 3.13 ran 29 tests,
28 passed and the Windows-only DPAPI test skipped. API pagination, retry ordering,
workflow/event separation and repeated stalled polling have regression coverage.
On the Pi, the changed checker read real Git/GitHub data for all four mapped
projects using a temporary database copy: the original CLI E2E project's exact
commit passed CI; the other three commits actually contain no workflow. No live
project was deliberately failed or re-executed for that check.

After idle-state verification and controller restart, the live dashboard/TUI
restoration test passed again with request
`71fdb60e-caeb-4be7-936a-6cee05edba9d`. UserTestProject remained paused, its original
session/cwd were confirmed, no goal was invented, and Infrastructure had no
resume error. The separate delayed-ack/error browser fixtures also passed.
