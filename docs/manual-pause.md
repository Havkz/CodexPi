# Durable manual pause and real quota evidence, 2026-09-24

## Pause authority

Previously the native `paused` state represented both an explicit user pause and
ordinary queue suspension. Automatic queue advancement could not distinguish
them. Windows reconnect also attached the TUI directly and overwrote its resume
intent without an operation ID. This bypassed the common acknowledgement path.

`manual_pause/<project-id>` is now persisted in SQLite before a manual pause's
native RPC. Dashboard Pause/Pause all, native pause and native goal clear latch
it. The native state vocabulary is unchanged. Explicit Resume or native goal
activation clears the hold; preemption does not create a manual hold. Pause all
also cancels pending queued resume requests. Pause is available on queued
projects, not only the currently selected project.

Queue advancement, restart recovery, Unsnooze and Windows reconnect share the
same automatic-resume eligibility check. A user-decision blocker, manual hold,
unfinished lifecycle or pause-all excludes automatic execution. Windows wake
uses a unique durable resume operation consumed by the same bounded TUI path,
not a second restoration implementation. Native turns cannot bypass a hold even
if a stale selected-project mapping survives. Delete removes the hold mapping.

On the first upgrade, legacy paused projects without a valid pending Resume
are held until explicit Resume: their original pause intent is unknowable, so
the controller does not guess permission to execute them.

Tests cover SQLite reopen, recovery after Pause intent but before native status
changed, stale resume cancellation, native TUI pause/activation, Windows reconnect
deduplication and legacy paused rows. The current suite has 40 tests: all passed
on Windows; the Pi run passed 39 with the Windows-only DPAPI test skipped.

`Setup/verify-pause-policy.py` created only project
`f0b86928-1a8b-4696-94c8-346b3c2730bd`, native session
`01a0d516-8e33-7ed2-9d9d-dcea2562a7b0`. A short native `/goal` command created its
queued paused goal. The real dashboard then paused it, the controller restarted,
Resume queued it without preemption, and Pause cancelled that queued request.
Native status stayed paused with zero model tokens throughout. The selected
user-decision-blocked project retained its slot. The fixture was deleted through
the dashboard: native archive, no DB/tmux mapping, Discord 404, private GitHub
retention and recovery backup were verified. No user project was removed.

## Real usage-limit history

`Setup/verify-usage-history.py` is read-only. It inspects native rollout, SQLite
outbox/reset metadata and the actual Discord channel's complete available
message history for project `4b1ac552-e54f-41ac-9598-1328cdb252de`, native session
`01a0cf79-e7a6-74f2-adb7-66a6dcb6c46f` (originally usertestproject2, now
usertestproject3). This is not the deleted, originally goal-less UserTestProject.

Two real task completions returned provider error `usage_limit_exceeded`:

| Native turn | UTC error completion | Outbox event | Discord message |
| --- | --- | --- | --- |
| `01a0cf7a-2831-7000-806c-b69fcdf6e055` | 2026-09-23 18:14:46 | 8 | `1552382757034790943` |
| `01a0cf7a-90b4-7a71-875f-735423f81a5c` | 2026-09-23 18:15:12 | 9 | `1552382861540204565` |

Each separate native attempt has exactly one matching Discord message, not two
deliveries of one event. Both persisted and displayed reset timestamps are
`2026-09-23T22:42:16Z`, i.e. 2026-09-24 00:42:16 Europe/Berlin, sourced from native
account metadata. The verifier checks provider error codes, distinct turn IDs,
event timing, sent timestamps, message identity and the reset in each embed.
It never infers a limit from inactivity or mutates goal/quota data.

This proves genuine limit detection/persistence/notification for a new mapped
goal started during exhaustion. It does **not** prove a fully automatic reset
-> Unsnooze -> native resume cycle: the session became paused in the intervening
history and later ran through a separate queue transition. It is now blocked
because its objective was only `test` and needs the user's test scope. That
blocker is preserved. Full end-to-end reset acceptance, physical power-loss
testing and the delayed Windows migration remain open.
