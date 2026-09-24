# Explicit Pi deployment

Default projects stay in `~/CodexPi/projects/<slug>`. Deployment is opt-in only
when that project's goal explicitly requires a 24/7 Pi service. The single
executing native worker registers a plan using the existing local infrastructure
tool; this is not an additional end-user `codexpi` command:

```sh
codexpi-tool deploy-pi --goal-requires-24x7 --reason "exact goal requirement" \
  --health-command "python3 healthcheck.py" -- python3 service.py
```

Use relative project file arguments, a foreground service process and an
idempotent read-only health check with meaningful application assertions.
Neither command uses a shell. Use the project's mode-600 `.env` for secrets,
not command-line arguments. EnvironmentFile loading and the application itself
must use compatible environment-file syntax. The service runs as the Pi user,
not root; privileged installation still requires explicit authorization.

The controller rejects unselected/nonexecuting projects, paused-all state,
missing native goals, concurrent lifecycle operations, occupied destination
directories and unowned/symlinked service configuration. A successful request
means **scheduled**, not deployed. The plan is persisted in SQLite at
`deployment/<project-id>` and included in database backups.

After native completion, clean-tree/push/exact-commit CI checks run first. The
existing lifecycle journal then records these recoverable steps:

1. Stop any existing owned service, quiesce the native turn/TUI, cancel wakes.
2. Atomically move the owned working copy to `~/<slug>` on the same filesystem.
3. Preserve the native session ID and update its cwd/workspace/sandbox roots.
4. Write and validate `codexpi-project-<project-id>.service`, enable/start it,
   check actual active state, run the bounded application health check and
   confirm active state again.
5. Persist the new project path and verified commit before publishing Complete.

The unit uses user systemd, `NoNewPrivileges`, restrictive umask, control-group
shutdown and bounded restart bursts. User lingering is a setup prerequisite.
The controller does not make another working copy or launch another AI worker.
A health failure stops the service, blocks the native goal with a concrete
reason and leaves the moved session/path repairable through ordinary Resume.
An incomplete filesystem/session step keeps its journal and fails closed.

Rename stops the owned service before moving files and regenerates/rechecks its
same stable project-ID unit at the new path. Delete disables/stops the service,
archives the native session, moves project data to the recovery backup, removes
the unit and deployment mapping, and retains the private GitHub repository.
The deletion manifest also retains the deployment plan for deliberate recovery.

## Evidence, 2026-09-24

`tests/test_deployment.py` covers admission/ownership, pending CI, failed health,
the sole working-copy move, native identity preservation, rename/delete and
crashes after quiescence, directory move, native remapping and service start
before the final database commit. The latter confirms recovery does not launch
a second service process. These are simulated process-crash boundaries, not
physical power-loss testing. The final rerun including queue follow-up tests had
37 Windows tests pass; Pi Python 3.13 ran 37, 36 passed and one Windows-only DPAPI
test skipped.

`Setup/verify-deployment.py --start` created only dedicated project
`3cfa4749-fcb7-4a57-9feb-2b67ecc7ab54`, native session
`01a0d39a-527a-7e63-bd25-2f5ba054228d`. The long TUI paste was submitted as a
prompt; the worker created a genuine native goal with the observed objective
recorded in the verifier. No native state/objective was fabricated or replaced.
The initial test composer needed one additional Enter, not a duplicate prompt.

The native worker built/tested the localhost-only HTTP fixture, registered its
plan and pushed `6bfb3c0a1678a15322f3f5a94e6101c924ff993f`. The controller moved it
to `/home/raspberry/codexpi-deployment-e2e-20260924`; the verifier independently
checked native cwd/session, absence of the old directory, clean Git tree, remote
SHA, active service and the exact HTTP response. This deliberately small fixture
had no workflow; it did not pretend to provide project CI evidence.

`--lifecycle` verified that controller restart preserved service PID `2003032`,
then used the actual dashboard to rename and delete this fixture. Native mapping,
Git origin, old-directory absence, service/DB removal, session archive, Discord
404 and private-repo retention passed. The retained repository is
`Havkz/codexpi-deployment-renamed-e2e-20260924`; its recovery backup is
`backups/deleted/3cfa4749-fcb7-4a57-9feb-2b67ecc7ab54`. Re-running the verifier now
observes the deleted fixture without creating or starting another project.

This does not certify OS reboot/power-loss behavior, Windows final delivery or
the pending Windows-session migration. Those remain in the overall audit.
The older UserTestProject resume verifier was not rerun successfully: that exact
fixture had already been deleted on 2026-09-23. It now explicitly reports a skip
instead of recreating it. The current `usertestproject3` requires a user-defined
test scope and was left blocked after verification.

The queue review also reproduced an existing handoff flaw: promoting another
project converted native usageLimited/blocked states to paused, which could
make them eligible for ordinary queue advancement. Promotion now preserves
inactive native statuses while still quiescing any turn. Automatic advancement
also rejects `requires_user` blockers. Three formerly failing regression cases
cover the two native statuses and a paused project carrying a user-decision
blocker. This is not a claim that all explicit-pause/reboot paths are audited.
