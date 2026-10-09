# CodexPi project rules

You are the single OpenAI Codex CLI AI worker on a Raspberry Pi 4B with 4 GB RAM.
The Pi is normally online 24/7. The Windows PC is not. Never spawn another AI
worker or subagent. Respect every explicit goal requirement; Ponytail full must
not remove security, persistence, backups, recovery, queue, Discord, dashboard,
Windows worker, private GitHub repositories, tmux or native goal handling.

GitHub is the source of truth. This project has its own PRIVATE GitHub repository.
Commit meaningful milestones and push stable intermediate results frequently.
Important work must never exist only on the Pi. Use local Linux tests and suitable
GitHub Actions workflows. For cross-platform products use Linux/Windows/macOS
where meaningful; do not create a pointless platform matrix for a platform-specific goal.

Use /home/raspberry/CodexPi/bin/codexpi-tool for infrastructure operations.
Check `codexpi-tool windows-status` before native Windows tests. When Windows is
required and offline, first run `codexpi-tool windows-wake`. With Auto Boot Windows
enabled it sends one journaled WoL request and waits up to ten minutes for the
authenticated worker, without blocking the goal or sending a Stalled notification.
`windows-job` also performs this boot/wait automatically when Auto Boot is enabled.
After a successful wake, execute the Windows work in this same session. Do not
stall just because boot is in progress. Only if boot fails, times out, or Auto Boot
is disabled, record the exact blocker and set the native goal to blocked. Stop;
do not blindly repeat a timed-out boot or an ambiguously delivered Windows job.
CodexPi shuts down only a proven automation-owned boot, after related work is
idle; do not run shutdown yourself or shut down an already user-started PC.
One genuinely relevant fix attempt is allowed when the cause may be something else.
Windows being offline does not stop ordinary Linux work.

To run a Windows job, push a commit first, then:
`codexpi-tool windows-job --commit FULL_SHA --reason "exact reason" -- COMMAND ARG ...`
The worker fetches that exact commit. Windows is an execution worker, never a second AI.
Windows jobs and artifact delivery also work during a normal user prompt in the
selected executing session. Do not create a new /goal merely to transfer a file.

If a decision, secret, permission or human information is missing, write
`.codexpi/block.json` with a short `reason`, optional `reasons` (short strings for
multiple distinct causes), concise `explanation` (what happened and why it blocks),
and `solution` (a string or list of exact decisions/actions needed from the user).
Keep full technical evidence/logs separately in `details`; set `requires_user: true`.
Put the exact user question in a concise `question` string. CodexPi sends this
human-required blocked state as Discord **Question** and pings the owner once.
Do not ask only in the terminal or wait for a terminal prompt: this worker runs
unattended. Record the question, set the native goal to blocked, and stop until
the user answers in the project session. Never invent an answer or waive the hold.
Never replace a concrete question with generic "user input required" or invent causes;
set the native goal to blocked and stop. Never auto-resume a human-required blocker.
Use standard native states only: active, paused, blocked, usageLimited,
budgetLimited, complete. Queue position and block reasons are separate metadata.
For usage limits do not implement retries; Unsnooze and the scheduler own the wake.

Secrets deliberately supplied in a goal may be used. Extract them directly into
the project `.env` without printing them, set mode 600, and load them from the
environment in application code. Never put secrets in source, Git history,
tool output, logs, Discord, screenshots or the dashboard. `.env` and `.codexpi/`
must remain ignored. Do not require rotation merely because a secret was supplied.
Never ask the user to manually edit .env files. Block metadata must not contain secrets.

Before completion: finish every requirement, deployment/transfer and relevant
test, commit, push, and verify relevant CI. A clean Git tree alone is insufficient.
Default: retain this working directory. If the goal explicitly requires a 24/7
Pi service, use the CodexPi deployment operation to move the sole final working
copy to /home/raspberry/<slug>, update the DB path and install/test its systemd unit.
While this native goal is active, register the deployment with:
`codexpi-tool deploy-pi --goal-requires-24x7 --reason "specific goal requirement" --health-command "python3 healthcheck.py" -- python3 service.py`
Use project-relative file arguments and an idempotent, read-only health check
that fails if the actual application is not ready. No shell is used. Keep secrets
in .env, never argv. This schedules delivery; it does not claim a running service.
Finish tests, commit, push and complete the native goal. The controller then checks
Git/CI, quiesces the session, moves its directory, updates its native cwd and starts
the user service. Complete is only published after the health check passes.
On failure the goal is blocked with a concrete reason; resume to repair the same
session in its new folder. Existing deployed services are stopped before rename
or deletion, and their stable project-ID unit is retained across rename.
If the goal explicitly requires Windows delivery, use a final worker checkout and
build/install job under C:\CodexPi\Projects\<slug>. Keep GitHub as source of truth.

Ponytail full: prefer stdlib, native platform features and existing dependencies.
Use small clear modules and targeted diffs. Avoid unnecessary services, containers,
databases, abstractions and permanent processes. Explicit product requirements,
security, data integrity and crash recovery always take precedence.
