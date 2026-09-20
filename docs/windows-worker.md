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
and interrupted-ledger recovery. Login/reboot, prolonged disconnect and
complete project lifecycle acceptance are still outstanding.
