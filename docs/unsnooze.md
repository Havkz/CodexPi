# Unsnooze integration

Installed on Pi: Unsnooze 1.19.0. Inspection on 2026-09-21 covered package.json,
`--help`, `status --json`, `doctor`, and the installed `src/cli.js`,
`src/resumer.js`, `src/agents/codex.js`, and `src/settings.js`.

Unsnooze remains a limit detector and reset-time source. CodexPi consumes its
structured session records and native account reset metadata; it does not implement a second banner parser.
`autoResume=false` is configured persistently and enforced by environment in
both systemd units (also inherited by their tmux/Unsnooze children). Codex's
configured wake message is `/goal resume`; tmux is the configured multiplexer.
The upstream CLI health/status command is polled every 60 seconds when idle,
and every 10 seconds when a selected goal is usage limited. Its real Pi cost was
measured at 1.54 wall seconds / 2.23 CPU seconds per call; this avoids continuous
Node cold-start overhead without replacing Unsnooze's own detection logic.
The dashboard shows the actual last-check timestamp.

## Why the manual CLI wake cannot be used safely here

`resume-now KEY` is selective but asynchronous: it sets `manual=true`, then
lets the daemon act later, independently of the controller's queue lock.
`preview` cannot remove the race between inspecting a pane and waking it.
If the pane disappears, 1.19.0's Codex adapter returns
`resume ID MESSAGE` with `messageViaPane=false`. The resumer then opens another
window with the message in argv, not as a slash command, and without CodexPi's
mapped remote bridge by default. The CLI has no live-pane-only/no-reopen switch.
Adding extra CLI arguments would not fix slash-command delivery or queue races.

The minimal fallback therefore reuses CodexPi's existing resume path, not an
Unsnooze fork or its private mutation API. A due, non-fallback reset for the
selected, ready, queue-position-1 usage-limited project becomes a durable SQLite
resume operation. Only then is that project's detector record cancelled.
CodexPi reopens the exact stored native session through its admission gate if
necessary, waits for the native TUI resume acknowledgement, then types the real
`/goal resume`. No goal text is constructed or submitted as an argv prompt.
Pause-all, lifecycle work, changing selection or lowering priority prevents
dispatch. A priority change discards the unsubmitted automatic wake. The existing
native gate also checks the actual incoming goal/turn operation under the lock.

The journal survives cancellation/restart. Submission is recorded and not
repeated while waiting for native acknowledgement; an acknowledgement timeout
is surfaced as an error rather than triggering an uncontrolled retry loop.

## Verification boundaries

### Overnight missed wake, 2026-10-06

Donut was resumed at 23:42 on October 5 while already exhausted. Its real native
turn failed with `usage_limit_exceeded` and the goal became `usageLimited`.
The persisted native-account reset was October 6 at 02:57:28 Europe/Berlin.
Hourly SQLite backups through 06:18 retain that reset, selected project,
queue position 1, no manual hold, no pause-all and no pending resume operation.
This was not an inactivity inference or a lost selected project.

Replaying the actual transcript batch through installed Unsnooze 1.19.0 produced
zero candidates. Its token-count record had `limit_id=premium`, null primary
and secondary windows, and zero credits. The detector needs a recent exhausted
Codex sample before accepting this empty-premium record; it does not consume
the task-complete error. Starting while already exhausted lacked that sample.
CodexPi displayed the native-account reset but previously scheduled only from
Unsnooze session records. This mismatch caused the missed overnight wake.

The scheduler now accepts either persisted authoritative reset source, confirms
the native goal still reports `usageLimited`, and journals the same mapped-TUI
resume operation. If both exhausted windows/sources exist it waits for the latest
binding reset. Before sending the slash it atomically records that reset as
attempted. A still-limited result, crash, or lost acknowledgement cannot trigger
another automatic attempt for that reset. A later genuine reset can. Cancellation
before submission does not consume the attempt. Deletion removes its marker.
No upstream fork, banner parser, extra daemon, or independent AI session is added.

Focused regressions cover the missing-detector-record case across DB reopen,
manual holds, once-per-reset submission, and a subsequent distinct reset.
These are simulations of scheduling, not proof of a real provider refill.

### Auto Continue

The dashboard switch above Queue persists `auto_continue` (default false).
Only a selected native `blocked`/`budgetLimited` goal may yield its slot, after
confirmed turn idleness and with no sent/running Windows job. Its own blocker
remains intact. The next eligible paused project uses the existing durable
resume path and acknowledgement. Usage limits keep their slot; manual holds,
pause-all and lifecycle gates remain enforced. Turning the switch off cancels
unsubmitted automatic handoffs. Completion handoff retains its existing behavior.
The regression exercises first-to-second-to-third selection, quota waiting,
user blockers, Windows work, switch-off and manually held projects.

`tests/test_scheduler.py` covers due/future/fallback resets, wrong sessions,
excluded goal states, pause-all, priority changes, durable reopen after simulated
restart, exactly one slash submission, and no `resume-now`/argv wake. These are
simulated scheduler decisions, not a manufactured provider usage limit.
Automatic provider-reset continuation acceptance remains outstanding; Codex
limits are not modified to force the test. `manual-pause.md` and
`Setup/verify-usage-history.py` now prove genuine provider-limit errors, persisted
resets and exactly one Discord message per native attempt. Ordinary real native
resume is tested separately. Manual holds and user-decision blockers also prevent
automatic wake, including a stale already-journaled wake after restart.

Live check on 2026-09-21: `Setup/verify-live-resume.py --resume` resumed the
existing queue E2E native session `01a0bbef-d4d2-7a63-9ebb-40495fa41952` from
stalled after the prior Git/network infrastructure repair, with its original
objective unchanged. The mapped TUI was absent before the test. Native active
acknowledgement was received, while the other project remained paused. The goal
then completed with a clean tree and remote main SHA
`4e630a892c9e17fe18d6bdb3a000e8133ee66214`; `QUEUE_TEST.md` contains
`queue-resume-ok`. The repository remains private. The completed TUI was released
and the next stored session `01a0bbea-00c6-7710-98f2-6b75a3099636` automatically
became active at position 1. That second goal later stalled on a separate native
Windows checkout credential failure; its Linux tests and GitHub CI passed.
This establishes real mapped resume/completion/queue handoff, not provider-limit
detection. Do not rerun `--resume` on the completed goal; the default is read-only.

`unsnooze doctor` reports the detector daemon running, plus missing generic shell
wrappers and the Claude StopFailure hook. CodexPi explicitly uses `_run codex`;
Claude is disabled and is not a second agent. These warnings are not proof of
Codex wake failure and do not justify installing unrelated Claude hooks.
