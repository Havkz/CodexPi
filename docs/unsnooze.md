# Unsnooze integration

Installed on Pi: Unsnooze 1.19.0. Inspection on 2026-09-21 covered package.json,
`--help`, `status --json`, `doctor`, and the installed `src/cli.js`,
`src/resumer.js`, `src/agents/codex.js`, and `src/settings.js`.

Unsnooze remains the limit detector and reset-time source. CodexPi consumes its
structured session records; it does not implement a second banner parser.
`autoResume=false` is configured persistently and enforced by environment in
both systemd units (also inherited by their tmux/Unsnooze children). Codex's
configured wake message is `/goal resume`; tmux is the configured multiplexer.

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

`tests/test_scheduler.py` covers due/future/fallback resets, wrong sessions,
excluded goal states, pause-all, priority changes, durable reopen after simulated
restart, exactly one slash submission, and no `resume-now`/argv wake. These are
simulated scheduler decisions, not a manufactured provider usage limit.
Real provider limit/reset acceptance remains outstanding; Codex limits are not
modified to force the test. Ordinary real native resume is tested separately.

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
