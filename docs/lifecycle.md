# Project lifecycle

Rename and Delete are available in the current-project controls and Project
Detail. Both use the existing authenticated, CSRF-protected dashboard API.

## Rename

The project is paused before changing its name. Pending Windows jobs, duplicate
names/slugs, occupied target folders/repos and ownership mismatches reject the
operation before it starts. A SQLite backup precedes the durable operation journal.

The journal records old/new mappings and each completed phase:

1. Pause the native goal, interrupt/wait for its turn, clean its background
   terminals, cancel wakes and stop its exact tmux session.
2. Rename the existing private GitHub repository by stable repository ID.
3. Atomically move the owned project folder and update its Git origin.
4. Retain the same Codex session ID; update native cwd/sandbox roots and name.
5. Rename the owned Discord channel.
6. Atomically update display name, slug, path, repo and tmux mapping in SQLite.

The renamed project stays paused until explicitly resumed. Reopening it through
`codexpi` attaches the same native session using the new folder and tmux mapping.
Native name/cwd operations were checked against the installed 0.155.1 schema,
source and [official App Server documentation](https://learn.chatgpt.com/docs/app-server).

## Delete

The exact current project name must be typed into the confirmation dialog and
is independently checked by the server. The UI explicitly describes its scope.

Delete pauses/stops the project, archives its native session, atomically moves
Pi project data into `backups/deleted/<project-id>/project`, deletes its owned
Discord channel, and removes its SQLite/tmux association. A manifest alongside
the backup retains the old mapping. GitHub is retained by default and deleted
only with the explicitly selected confirmation option. Existing Windows
worker checkouts remain; they are disclosed in the confirmation dialog.

Recovery backups include the project's `.env`; they are private local backups,
not served by the dashboard or committed to Git. No automatic purge is performed.
Restore is an administrator operation using the manifest and SQLite snapshot;
do not blindly copy an old whole database over newer work.

## Interrupted operation recovery

Each external step is idempotently checked on retry. The journal is not erased
by pause. Unfinished projects cannot start model turns, accept jobs or be opened
as fresh projects. Startup and the scheduler retry pending operations, with
30-second backoff and a visible error. Recovery rolls forward to the requested
state, without creating another session or replacing another project's resources.

Native 0.155.1 `thread/list` omits empty sessions. Exact `thread/read` still
returns the authoritative archived rollout path; Delete checks that path before
repeating archive and verifies it afterwards. Repeating archive unconditionally
would fail after a crash immediately following archival.

Discord's completion Close action also retains a journal for retry after a crash;
it removes only the channel, not the project.

## Verified on 2026-09-20

- `tests/test_lifecycle.py`: crash injected after each side effect, before its
  journal acknowledgement; SQLite reopened; all five Rename and four Delete
  boundaries recover. Exact-name confirmation, ownership and pending-job guards
  reject unsafe operations. These are deterministic simulations, not power-loss tests.
- Live browser test: `Setup/test-live-lifecycle.py` created only
  `CodexPi Lifecycle E2E 20260920`, renamed it to
  `CodexPi Lifecycle Renamed E2E 20260920`, reopened the same session, rejected
  a wrong Delete confirmation, then confirmed deletion.
- Project `b0407e0f-ca54-4d5b-84db-6de77a4d536e`; native session
  `01a0bff6-8d6c-7990-b011-2b6ad7efc91c` preserved through Rename and archived by Delete.
- Verified native name/cwd, Git origin, absence of old/new active project folders,
  absence of DB/tmux association, Discord API 404, local recovery backup and private
  retained repository `Havkz/codexpi-lifecycle-renamed-e2e-20260920`.
- Windows unit suite: 13 passed. Pi suite: 12 passed, DPAPI test correctly skipped.
- Existing dashboard security and four-width browser checks still pass.

Still required for final acceptance: live process-crash/reboot tests; completed
deployment lifecycle; direct TUI `/rename` integration; rename consistency for
previously deployed services/Windows checkouts; full native-goal/queue regressions.
The verified live lifecycle session was empty: stopping an actively generating
model turn is covered by the shared pause implementation/tests, not by this live test.

2026-09-24: the Pi deployment lifecycle and deployed-service Rename/Delete now
have unit/crash-boundary and real native-session evidence in `deployment.md`.
The live deployed fixture was complete before Rename/Delete; this does not
retroactively claim an active-turn interruption or physical power-loss test.
