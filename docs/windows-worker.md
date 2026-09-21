# Windows worker

The worker is infrastructure, not another Codex agent. It connects outbound to
`ws://192.168.2.105:8787/worker/ws`; no Windows inbound listener is created.
Both sides authenticate every application message with a shared random HMAC
key, a per-connection challenge, sender, monotonically increasing sequence,
and a timestamp (60-second tolerance). Keep Windows and Pi clocks synchronized.
HTTP/WebSocket content is not encrypted on this LAN; SSH protects provisioning.

## Installation and autostart

`Setup/configure-worker.py` retrieves only WORKER_SECRET using the existing SSH
credential and stores a CurrentUser DPAPI encrypted blob in the ignored
`windows-worker/config.json`. It does not print the key. Run it with
`C:\CodexPi\.venv\Scripts\python.exe` as the actual Windows user.

Run `Setup/install-worker.ps1` elevated as the same user. It preserves an
existing task definition, restricts the worker directory ACL, then registers
`CodexPi Windows Worker`: Interactive user, Highest, Hidden, IgnoreNew,
unlimited duration, restart-on-failure, AtLogOn and StartWhenAvailable.
The executable is `C:\CodexPi\.venv\Scripts\pythonw.exe`; its working directory
is `C:\CodexPi`, arguments `-m app.windows_worker`. Git and gh credentials remain
those of the signed-in Windows user, not SYSTEM. No password is stored in the task.

Check `Get-ScheduledTask -TaskName 'CodexPi Windows Worker'` and its Principal
and Settings properties. Running is not sufficient proof of connectivity:
also check the dashboard or the Pi's `codexpi-tool windows-status`.
Only one worker process can hold `windows-worker/state/worker.lock`.

For a controlled worker restart, first verify that no job is running, stop this
task, wait until its state is `Ready` and its old worker process has exited, then
start it. `IgnoreNew` can discard a start requested while termination is still
in progress. Verify the signed connection/heartbeat afterward, not just task state.

## Protocol and jobs

After the signed handshake the worker sends its durable job inventory, then
exactly one `alive` body every 20 seconds. Only a valid alive establishes online
status; 60 seconds without one makes it offline. Results and other messages do
not extend that deadline. Connection loss uses exponential backoff capped at
30 seconds with small jitter. Jobs continue locally across a network disconnect.

Each job carries a UUID, repository, normalized slug, exact 40-character SHA,
argv array, 1–7200 second timeout and project-relative artifact paths. GitHub is
the synchronization source. The worker checks out under
`C:\CodexPi\Projects\<slug>`, validates origin and SHA, and refuses to overwrite
local changes or an unrelated existing checkout. Commands run without a shell
wrapper and without visible console windows. Timeout kills the process tree.

All checkout Git commands use a process-local empty `credential.helper` reset
followed by `!gh auth git-credential`, and `GIT_TERMINAL_PROMPT=0`. This uses the
already authenticated user's gh keyring and does not ask the background task to
persist a new credential through Git Credential Manager. No token is copied into
arguments, files, or job output. Global Git configuration and the actual test
command's environment are not changed. The same path covers initial clone and
subsequent exact-SHA fetches. See the official
[Git helper reset semantics](https://git-scm.com/docs/gitcredentials) and
[GitHub CLI credential-helper support](https://cli.github.com/manual/gh_auth_setup-git).
Output is bounded to 2 MiB per stream and drained, with truncation indicated.
Responses include stdout, stderr, exit code, timeout/truncation flags, exact
commit, actual cwd, elevation flag and resolved existing artifact paths.

The WAL/FULL-sync SQLite ledger records acceptance before starting a command.
Same-ID deliveries never execute twice. Completed results are retried after
reconnect until acknowledged. A process restart during execution produces an
explicit unknown-outcome result; it does not blindly repeat side effects.
The controller reconciles unacknowledged delivery against the worker inventory.

Logs rotate at 2 MiB with five backups under `windows-worker/logs`. The shared
secret, project `.env` values, and common GitHub/API token formats are redacted
before returned output is persisted. Do not put credentials in command arguments.

## Verification status

See `progress.md` for the exact live job ID, SHA and observed elevated result.
Unit tests cover native output/exit/timeout, path validation, DPAPI roundtrip
and interrupted-ledger recovery, plus scoped authentication on both clone/fetch.

On 2026-09-21, real task job `6f1c5f44-13a8-4df7-a74d-0102f700b4c2` fetched exact
SHA `4138f9930e788ca181c308991c525343d4517a93` and passed all three native Windows
unittests in `C:\CodexPi\Projects\codexpi-e2e-20260920`, with exit 0 and elevation
true. The result was acknowledged (`delivered` in the worker ledger). The original
Pi Codex session submitted this job after reconnect automatically lifted its
recorded Windows-offline-only blocker; it then completed its original goal.
The Windows working tree was checked clean. Before the fix, three recorded jobs
failed before checkout with `wincredman` and missing `/dev/tty` errors. The user's
global helper remains `manager`; only worker Git children use gh.

This verifies real reconnect and exact-commit execution, not Windows reboot/login
autostart, the precise 60-second heartbeat expiry, or every interrupted-job case.
Those acceptance checks remain outstanding.
