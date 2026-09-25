# Architecture and data ownership

## Process and trust boundaries

| Component | Responsibility / interface |
| --- | --- |
| `codexpi.service` | `app.main`: dashboard/API, Discord bot, scheduler, lifecycle recovery and worker connection in one Python asyncio process |
| `codexpi-native.service` | One official Codex app-server, private Unix socket `state/native.sock`; multi-agent disabled |
| `codexpi-unsnooze.service` | Upstream detector daemon, automatic upstream wake disabled; controller decides eligible wakes |
| Mapped tmux TUI | Native Codex user interface attached through `state/tui.sock`, not directly to the native socket; inactive detached TUIs released |
| Windows scheduled task | Outbound authenticated worker only; no second AI and no inbound remote-shell listener |
| `bin/codexpi` | Interactive `/rename` entrypoint through `state/local.sock`, then exact tmux attachment |

Units live in `config/` and are installed in
`/home/raspberry/.config/systemd/user/`. They use `Restart=always`, five-second
restart delay, `UMask=0077`, explicit PATH and working directory. A process flock
on `state/controller.lock` prevents duplicate controllers. Native and Unsnooze
are separate units; restarting the controller does not deliberately restart them.
Linger starts the user manager without interactive SSH login. Network ordering
is not a promise of internet readiness; components still reconnect after failures.

The dashboard binds the configured private Pi address, port 8787. Its middleware
enforces LAN address/Host, server-side password authentication, expiring sessions,
CSRF/Origin checks and login throttling. Cookies are HttpOnly/SameSite=Strict;
Secure is used only over HTTPS. The current LAN HTTP deployment is **not TLS**.
Worker messages are HMAC-authenticated but not encrypted by the WebSocket layer.
Do not expose port 8787 to the internet. Unix sockets are mode 0600; they trust the
local `raspberry` account, not an isolated adversarial user with that account.

## Modules and files

- `app/controller.py`: single-project selection, pause/resume acknowledgements,
  native-state reconciliation, CI/completion gating, polling and periodic backups.
- `app/native.py`: native RPC client, upstream goal-status reader, narrow TUI
  admission gate. Native `/model` permits only its verified model/reasoning batch.
- `app/lifecycle.py`, `app/deployment.py`: durable, ownership-checked external
  effects and roll-forward recovery for rename/delete/channel close/deployment.
- `app/db.py`: SQLite migration, constraints, transactions, backup and usage history.
- `app/discord_bot.py`: project channels, persistent status outbox and Close action.
- `app/web.py`, `app/web_assets/`: authenticated state/actions, details, history,
  responsive dashboard and existing-logo favicon; no public create-project API.
- `app/worker_server.py`, `app/windows_worker.py`: signed protocol, job lifecycle,
  exact-SHA checkout, bounded output and durable job ledger.
- `templates/AGENTS.md`: generated project operational requirements, separate
  from the user's native `/goal` objective; `.codexpi/project-id` proves ownership.
- `config/site.json`: private generated installation configuration/password hash;
  `.env`: Discord token and worker secret. Neither is committed.
- `state/`, `logs/`, `backups/`, `projects/`: private runtime data, not source assets.

## Source of truth

Native Codex owns goal objective, history, status and session ID. CodexPi mirrors
native statuses; inactivity and an exhausted account snapshot do not invent a
native usage-limited goal. Upstream goal parsing is reused from the installed
`Setup/upstream/goal-hooks` checkout. Missing native context is never reconstructed
as a new prompt by the controller.

`state/codexpi.db` owns infrastructure mappings and authority: project ID, stored
native session ID, cwd, tmux, private GitHub repo, Discord channel, queue position,
manual hold, selected project and operation journal. It uses integrity checking,
WAL, FULL synchronous writes and foreign keys. Schema version 3 contains:

| Table | Durable purpose |
| --- | --- |
| `projects` | Unique names/slugs/paths/session IDs/tmux/repos/channels, queue and lifecycle; native status mirror, block reason, usage reset and resume result |
| `settings` | Selection, pause-all, manual holds, verified completion/deployment metadata and latest account usage |
| `sessions`, `login_attempts` | Hashed dashboard session IDs/CSRF/expiry and login rate limiting |
| `events` | Per-project status notification outbox with delivery acknowledgement |
| `jobs` | Windows jobs, delivery state, result and recovery reconciliation |
| `usage_samples` | Bounded real timestamped daily/weekly remaining-usage observations |

A partial unique index permits at most one `projects.goal_status='active'` row.
That constraint alone is not execution safety: the shared controller lock, native
TUI admission checks, stop/wait-before-switch and automatic-resume eligibility
checks enforce the runtime boundary too. Same-session ordinary/native commands
do not gain permission merely because their HTTP request succeeded.

## Queue, acknowledgement and recovery

Resume is nonpreemptive. Run now changes an actual priority order and quiesces
the previous worker before allowing another. Manual pauses survive restart and
cancel queued wakes. Windows-online recovery is allowed only for a recorded,
solely Windows-offline blocker without required user input. Completed/deleted
projects and user-decision blockers cannot automatically resume.

Resume persists a unique operation before restoring the mapped TUI. The gate
acknowledges the actual native session/cwd; only the intended session receives
the real `/goal resume`. Submission is journaled before sending and is never
blindly retried after an uncertain acknowledgement. Backend confirmation is
bounded to 60 seconds; the UI waits for the matching operation result, not HTTP
success, and has a 90-second confirmation limit. An empty session is restored
without fabricating a goal. See [lifecycle fixes](lifecycle-fixes-20260923.md).

Native completion still requires a meaningful committed/pushed exact SHA and
relevant GitHub Actions result before final completion notification or deployment.
Missing expected CI is pending, not success. Private GitHub is the committed-code
source of truth, not a backup of native history, uncommitted files or secrets.

Discord status changes and their outbox events commit together. Delivery retries
check the event marker in channel history, and a later reset update edits the
existing notification. Windows jobs use UUID deduplication and acknowledged
durable results; unknown interrupted side effects are not silently repeated.
See [worker protocol](windows-worker.md) and [Unsnooze](unsnooze.md).
