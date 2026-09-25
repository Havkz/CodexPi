# CodexPi installation progress

The authoritative specification is C:\CODEXPI_GOAL.md (2975 lines, including
the appended binding design, lifecycle, migration and usage-chart requirements).
`requirement-audit.json` preserves every nonempty source line for individual
evidence assignment. A pending item is not implemented or verified merely
because a related file exists. The dashboard password is deliberately omitted.

## 2026-09-25 usage-history implementation (live deployment pending)

`docs/usage-history.md` records the bounded persistent measurements, independent
Daily/Weekly line-area charts and remaining-usage progress cards. Local automated
and isolated responsive-browser checks passed; Pi installation and live history
checks are pending because both SSH and dashboard TCP connections currently fail.
The earlier manual-pause correction is published as `877016b`; all four jobs in
GitHub Actions run `36056051967` passed. No overall completion is claimed.

## Verified 2026-09-19

- Windows 11 Home; Node 24.14.0, npm 11.14.1, Git 2.51.0, gh 2.88.1,
  OpenSSH 9.5p2, Codex 0.155.1. GitHub account: Havkz.
- Pi SSH works as raspberry@192.168.2.105. Ubuntu 25.10 / aarch64,
  Node 22.22.3, npm 10.9.8, Python 3.13.7, Git 2.51.0, tmux 3.5a.
- Pi has 3.7 GiB RAM, 5.8 GiB free storage at initial inventory.
- Existing projects and services: Pwnagotchi-Discord-Pi and Vertretungsplan.
  They must remain undisturbed. Port 8787 was unused.
- Before installation, shell/npm configuration backups were saved under
  `/home/raspberry/.codexpi-preinstall-backups/20260919-151853`.
- Official standalone Linux ARM64 Codex 0.155.1 installed under `.codex/packages`.
  Installer added `.local/bin` to `.bashrc`.
- ChatGPT login verified after user completed device authorization.
- Unsnooze package is 1.19.0; executable currently in
  `/home/raspberry/.local/node_modules/.bin/unsnooze`.
  `--version` is not supported; version is read from package.json.
- User systemd works, `loginctl show-user raspberry -p Linger` reports yes.
- sudo requires interactive authentication except for an unrelated existing
  pwnagotchi restart rule. Firewall inspection still requires elevation.

## Verified 2026-09-20 (incremental, not final acceptance)

- Pi user services `codexpi`, `codexpi-native`, and `codexpi-unsnooze` are
  enabled and running. Discord gateway connected; user has invited the bot.
- All seven reviewed goal/Ponytail hook definitions are natively trusted.
  Backup: `backups/hook-trust-1789858181269498095.toml` on Pi.
- Dashboard at `http://192.168.2.105:8787` passes live authentication,
  wrong-password, cookie, CSRF, Origin, Host, no-secret-state, and logout checks.
  Reproduce with `Setup/verify-dashboard.py` on this Windows machine.
- Thirteen local unit tests pass, including concurrent login rate limiting,
  SQLite constraints/rollback/backups, HMAC replay prevention, native Windows
  subprocess output/exit/timeout, interrupted-job handling and DPAPI roundtrip.
  Reproduce: `.venv/Scripts/python -m unittest discover -s tests -v`.
- Windows task `CodexPi Windows Worker` is Running, Interactive as User,
  Highest, Hidden, IgnoreNew, no execution time limit. Credential is CurrentUser
  DPAPI encrypted and worker directory ACL restricted to User/Admins/SYSTEM.
  A Windows login/reboot autostart test is still outstanding.
- Worker connects outbound; live dashboard reports Windows online. Native
  job `9a189ce0-4da5-4e30-bd0f-4ff82f28f25c` checked out private repository
  `Havkz/codexpi-e2e-20260920` at exact SHA
  `66936692e45ba99e5686ce48c874825dcd4a5075`, ran as administrator on win32,
  returned stdout, distinct stderr, exit 0 and an existing README artifact path.
- E2E project ID `b94e2023-f126-49c2-82b6-039771e8914e` has a private GitHub
  repository and Discord channel `1551005513758543936` in the specified category.
- `codexpi.cmd` is installed in the user PATH (new terminal required).
- Found and fixed initial native session materialization: `thread/start`
  alone does not persist history; native `thread/inject_items` records only an
  initialization instruction, without a model turn or invented user goal.
  TUI restart and goal/queue acceptance are still being tested.

## Verified 2026-09-21 (incremental, not final acceptance)

- Re-read all 2900 source lines, including the 36 mandatory design sections.
  Source SHA256 remains `23cfddb164d6cb21ce9eb362bbcdbf2d979365c9013f0c1d153223a230e15335`.
  All 681 nonempty design lines are represented in the existing audit.
- Unsnooze 1.19.0's asynchronous dead-pane CLI revival was found to use an argv
  prompt. The controller now journals a due selected wake and reuses its native
  mapped-TUI resume path; no extra detector, private API adapter, or fork.
  See `unsnooze.md` for source evidence, regression checks, and limits.
- Fifteen Windows unit tests pass. On Pi, fourteen pass and Windows DPAPI is
  skipped. Added coverage includes detached idle-TUI release, TUI RPC admission,
  deferred TUI rename, native resume clearing stale blockers, and selective wake
  across simulated SQLite reopen, pause-all, priority change, and missing panes.
- Live queue E2E resumed the original stored native goal, pushed verified remote
  SHA `4e630a892c9e17fe18d6bdb3a000e8133ee66214`, completed, released its TUI,
  and automatically resumed the next original session without a parallel goal.
- The next CLI project passed Linux tests and GitHub CI at SHA
  `4138f9930e788ca181c308991c525343d4517a93`, then stalled on Windows Git
  credential-manager authentication. That specific checkout failure is the
  next diagnostic target; Windows job completion is not claimed.
- Existing block-reason cleanup missed native TUI resume because the admission
  gate recorded active before the poller saw the transition. Both paths now use
  shared cleanup; stale complete-project blockers are also reconciled.
- Ponytail review: reused the existing journal and TUI resume; no new runtime
  dependency or background process. No further safe simplification identified.
- Subsequently repaired the Windows checkout authentication at the shared Git
  child-process entry point, covering both clone and fetch. No global Git or
  credential-store changes. Live acknowledged elevated job
  `6f1c5f44-13a8-4df7-a74d-0102f700b4c2` passed all three tests at exact SHA
  `4138f9930e788ca181c308991c525343d4517a93`. The original CLI E2E goal then
  completed; both test goals are complete and retain their original session IDs.
  Native Linux tests, clean Pi/Windows trees, remote main SHA and successful
  GitHub Actions run `35543242446` were independently checked.
- Seventeen Windows unit tests pass; sixteen Pi tests pass with one DPAPI skip.
  Idle Unsnooze polling was reduced from ten to sixty seconds after measuring
  approximately 2.23 CPU seconds per CLI invocation. Usage-limited selected
  goals retain ten-second polling. No new service, parser or dependency added.
- Warm 60.10-second idle measurement with both native goals complete and no
  tmux panes: 364.76 MiB process PSS, 255.45 MiB cgroup MemoryCurrent, 5.45%
  of one CPU core across all three Pi services. See `resources.md`; a final
  post-implementation measurement remains explicitly pending in the audit.

## Work still required

2026-09-24 follow-up: `manual-pause.md` records durable user-pause authority shared
by queue/recovery/Unsnooze/Windows reconnect, 40-test coverage and a real zero-token
native pause/restart/queued-resume/cancel/delete verification. Read-only native
history plus actual Discord messages now prove two genuine provider-limit
attempts were persisted/notified with their reset times. A fully automatic reset
and Unsnooze continuation remains unverified; do not conflate these evidence scopes.

2026-09-24: implemented the previously missing explicit Pi deployment operation
using the existing lifecycle journal. See `deployment.md` for 37-test Windows/
36-pass-one-skip Pi coverage, crash-boundary simulations and the real native
goal -> commit/push -> sole-directory move -> systemd -> application health path.
Controller restart preserved the app process; live dashboard rename/delete of
that deployed fixture passed with private GitHub/recovery backup retained.
No ordinary project was deployed or removed, and migration has not begun.

2026-09-23 lifecycle repair: see `lifecycle-fixes-20260923.md` for reproduced
causes, deployed fixes, 27-test Windows/26-test Pi evidence, live empty-session
restoration, real native goal execution/completion, live paused deletion with
pending resume, native `/model`, and sandbox enforcement. The original
specification was preserved and extended to include all new requirements.
Genuine provider-limit/reset end-to-end verification and the explicitly delayed
Windows project migration remain pending; no synthetic limit is claimed live.

Completion-gate follow-up: reproduced and repaired missing/partial/wrong-commit
CI acceptance, stale failed-attempt handling and repeated final-failure events.
29 Windows tests passed; 28 Pi tests passed with one Windows-only skip. Real
GitHub checks for all four mapped projects and post-restart dashboard/TUI
restoration passed. Details and conservative missing-workflow behavior are in
`lifecycle-fixes-20260923.md`; this remains incremental, not final acceptance.

The dark dashboard redesign is deployed and has incremental live desktop/mobile
and synthetic interaction evidence in `docs/design-verification.md`. A genuine
browser form-login Origin defect was found and repaired without weakening the
Origin check. This is not final design or lifecycle acceptance.

The appended design sections 1–36 are mandatory acceptance criteria: unified
dark design tokens, polished responsive login/dashboard/detail/infrastructure,
semantic web status pills, accessible controls, and compact native Discord
embeds with multiline vertical indentation and a random readable accent per
message. Verify 1920x1080, 1440px and 375–430px widths, all embed types/buttons,
and regression coverage for every security, queue, recovery and lifecycle path.
No existing functional requirements are replaced by this addition.

Dashboard Rename/Delete have live and simulated-crash evidence in `lifecycle.md`.
Full TUI/goal/queue verification, remaining rename/delete/deployment integration,
crash/reboot/worker disconnect tests, final CI and source publication,
resource measurement, comprehensive documentation and per-line requirement audit.
The overall goal is not complete. Passing the checks above does not certify
the untested lifecycle and scheduling paths.

## Source references

- https://learn.chatgpt.com/docs/codex/cli
- https://learn.chatgpt.com/docs/hooks
- https://github.com/mhmdibrahimm/codex-goal-hooks
- https://github.com/saaranshM/unsnooze
- https://github.com/DietrichGebert/ponytail
