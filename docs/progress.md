# CodexPi installation progress

The authoritative specification is C:\CODEXPI_GOAL.md (2900 lines, fully reread
on 2026-09-20 including the appended binding design specification).
`requirement-audit.json` preserves every nonempty source line for individual
evidence assignment. A pending item is not implemented or verified merely
because a related file exists. The dashboard password is deliberately omitted.

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
- Eleven local unit tests pass, including concurrent login rate limiting,
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

## Work still required

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

Full TUI/goal/queue verification, complete rename/delete/deployment lifecycle,
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
