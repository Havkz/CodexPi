# Recovery and operator runbook

This describes the implemented recovery paths and their boundaries, not a claim
that physical power-loss or every boot scenario has passed live verification.

## Normal process recovery

systemd restarts failed units. `app.main` takes an exclusive controller flock,
opens/checks SQLite, starts the local gates, then runs `Controller.recover()`.
Lifecycle journals roll forward before queue reconciliation. It reads actual
native goals, preserves manual holds, pauses nonselected native activity and
reconciles persisted statuses. Only an eligible selected active goal gets its
same mapped TUI restored and a durable native-resume operation. Paused or
user-blocked projects stay inactive; complete never auto-runs. Usage-limited
goals wait for a real eligible Unsnooze reset. No new native goal is invented.

On controller recovery, the Windows worker reconnects with a new signed challenge
and durable job inventory. Only signed heartbeats establish online state. A native
bridge restart uses the same persistent Codex session history. The controller's
reconnect path invokes recovery again; it does not create a second worker.

## Safe diagnosis

Run on the Pi as `raspberry`:

```sh
systemctl --user status codexpi codexpi-native codexpi-unsnooze
systemctl --user show codexpi -p MainPID -p NRestarts -p ActiveState
loginctl show-user raspberry -p Linger
/home/raspberry/CodexPi/bin/codexpi-tool windows-status
tmux list-sessions
```

Check Dashboard -> Infrastructure and the project detail's stored native ID,
status, operation result and block reason. `logs/controller.log` is rotating JSON
with component names (controller, recovery, scheduler, Discord); 2 MiB per file,
five retained rotations. `journalctl --user -u codexpi` supplements it. Do not
paste raw logs or credentials publicly, even though application redaction exists.

An online Pi is not a successful native resume. If TUI acknowledgement timed out,
inspect the exact mapped pane/session first. Do not repeatedly issue resume,
launch a second direct Codex worker, clear the operation journal or change native
goal state by hand. A genuine provider-limit result is handled separately from
transport/identity/timeouts. A missing original goal needs the user's real prompt.

Before a planned service restart, verify there are no executing native turns or
pending Windows jobs. Do not restart unrelated Pi applications. Normal control:

```sh
systemctl --user restart codexpi
systemctl --user is-active codexpi codexpi-native codexpi-unsnooze
```

Restarting only the controller is different from rebooting the Pi or restarting
the native bridge. It still disconnects dashboard/TUI gate/worker connections
temporarily. Never use a restart as proof that native goal continuation works.

## Backups

The controller periodically uses SQLite's online backup API, checks integrity,
fsyncs, atomically publishes the snapshot and retains seven snapshots under
`backups/sqlite/`. Lifecycle operations also take snapshots. The live database's
`-wal`/`-shm` files are not optional when copying an open SQLite database; use
the provided backup method instead of copying only `codexpi.db`.

Manual consistent infrastructure DB snapshot on the Pi:

```sh
cd /home/raspberry/CodexPi
.venv/bin/python -c "from app.db import Database; d=Database('state/codexpi.db'); print(d.backup('backups/sqlite')); d.conn.close()"
```

This is **not a complete disaster-recovery backup**. Full recovery also needs:

- mapped project folders, `.git`, uncommitted/ignored work and protected `.env`;
- native Codex state/goal databases and mapped active/archived rollout files in
  `/home/raspberry/.codex`, preserving the original native session IDs;
- detector state/config in `/home/raspberry/.unsnooze`;
- CodexPi source, generated `config/site.json`, `.env`, goal-hook state and
  lifecycle/deleted-project backups;
- Codex configuration/hooks/instructions, installed upstream goal-hook parser,
  Ponytail configuration and user systemd units;
- Windows worker DPAPI configuration, durable ledger and any uncommitted Windows
  checkouts. DPAPI data is tied to its Windows user, not portable credentials.

For a complete local snapshot, first use the normal pause mechanisms and wait
for jobs/turns to finish, then stop the three CodexPi units. Preserve the files
above as one timestamped, access-restricted set. Shared native state may include
other sessions: preserve it, do not selectively rewrite SQLite rows. Credentials
and project secrets in these backups must remain private, outside Git, with
directory mode 0700 and secret files 0600. Copying files without a successful
restore drill is not evidence of disaster recovery.

## Restore procedure and stop conditions

1. Stop CodexPi units and prevent the Windows worker from dispatching pending
   work. Do not delete the current files; first preserve a separate recovery copy.
2. Inspect the candidate snapshot with SQLite in read-only mode and run
   `PRAGMA integrity_check` / `PRAGMA foreign_key_check`. Confirm schema compatibility
   and exact project/session/path/repo/channel mappings against native records.
3. Restore a coordinated snapshot, not an old infrastructure DB over newer
   projects. An old DB alone can resurrect deleted mappings or obsolete queue
   intent. Missing Discord channels, renamed repos, completed operations and
   unresolved Windows-job outcomes need explicit reconciliation before startup.
4. Preserve native session IDs and history. A Git clone alone cannot restore
   prompts, goals, manual holds or a pending resume. Do not manufacture them.
   Keep restored projects held until their native and external mappings agree.
5. Restore ownership/secret permissions and dependencies, validate user units,
   then start native/Unsnooze/controller services. Confirm database integrity,
   exactly one controller, actual native state, queue and worker reconnect before
   giving explicit execution authority through normal Resume.

There is currently no blind one-command whole-system restore or automatic
deleted-project resurrection. A deleted-project manifest records its former
mapping, while `backups/deleted/<id>/project` retains local work and GitHub remains
private. Reinstating that project must reconcile its archived native session and
removed Discord channel; copying a stale whole DB is unsafe. Do not claim this
operator procedure is a tested restore implementation until an isolated drill
has exercised the relevant snapshot and external-state reconciliation.

## Verification

`tests/test_core.py` covers SQLite constraints, transaction rollback, online
backup retention/integrity and refusal to overwrite corrupt data. Lifecycle and
deployment tests simulate crashes after external effects and before journal
acknowledgement. Usage tests prove real-observation storage survives reopening
and backup; real Pi controller restarts retained exact samples too.

`Setup/verify-controller-recovery.py` performs a read-only preflight by default.
`--crash` deliberately sends SIGKILL to **only the systemd controller main PID**,
after rejecting active native turns, goals, operations and unfinished Windows
jobs. It requires a connected Discord/worker baseline, then checks a new PID and
invocation, increased systemd restart count, unchanged native/Unsnooze processes,
same dashboard authentication, project mappings/queue/manual holds/native states
and retained real usage observations. It does not test active-model continuation,
native-process crash, reboot, kernel panic or physical power loss.

The Windows reboot/logon, full Pi reboot, active native crash recovery and
coordinated disaster-restore drills remain separate final audit requirements.

### Live controller crash, 2026-09-25

`Setup/verify-controller-recovery.py --crash` passed with four existing mapped
projects and no active goal/job. systemd replaced controller PID `163716` with
`165563`, incremented its restart counter and created a new invocation. The
native bridge and Unsnooze service PID/invocation/counter remained unchanged.
The original dashboard session and CSRF token still worked. Discord and signed
Windows heartbeat reconnected; project mappings, selection, native statuses,
manual holds and sampled history were identical/preserved. The user's
`usertestproject3` remained blocked, not resumed.

The local ignored evidence record is
`state/controller-recovery-20260925-194716.json`; it records completed=true and
explicitly automatic_active_goal_resume_tested=false. This is a real SIGKILL
process-recovery test, not a simulated status change or a whole-device reboot.
