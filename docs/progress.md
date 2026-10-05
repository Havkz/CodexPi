# CodexPi installation progress

The authoritative specification is C:\CODEXPI_GOAL.md (see the audit's exact line count, including
the appended binding design, lifecycle, migration and usage-chart requirements).
`requirement-audit.json` preserves every nonempty source line for individual
evidence assignment. A pending item is not implemented or verified merely
because a related file exists. The dashboard password is deliberately omitted.

## 2026-10-05 migration and final cleanup

The user confirmed the Pi restarts were unexpected, not their reboot test.
Read-only diagnosis confirms unclean shutdown/storage consequences but no
definitive trigger. Existing global 30-second hardware and forced Internet
watchdogs, a separate self-bot restart storm, and the older SD card require
attention; none is yet proven causal. No global services were changed. See
`pi-restart-investigation.md`. Large writes/deletions are currently held.

The selected Donut session has a checked private full archive on both hosts and
is registered on the Pi using its original native session ID. Original goal
fields and the full rollout prefix were verified. Final file verification found
four damaged/incomplete copies across Pi restarts; repair and live TUI acceptance
are not yet proven. See `migration.md` for evidence, exact scope and limitations.

The user owns the real usage-reset and full Pi-reboot acceptance tests; do not
claim either passed without their result. They also explicitly authorized
deleting all Codex-created test channels/repositories once no longer needed,
and subsequently included `usertestproject3`. Keep only the migrated Donut
project. Quiesce/archive through lifecycle deletion before external repository
deletion; preserve recovery data and evidence. Cleanup is not yet performed.

## 2026-10-01 native Optimizer execution and migration priority

The installed Optimizer now has one genuine completed native goal as evidence:
correct file/commit/private push, exactly one Discord completion, real checkpoint
with objective and continuation, unchanged Ponytail-full injection and redacted
goal-hook transitions. The existing verifier was extended, not a new test suite.
See `optimization.md` and `resources.md` for identities, scope and measured idle
usage. Cached quality metrics are not claimed as live tool counts or savings.
Commit e873640 passed all four GitHub Actions jobs in run 36748225324.

The user has now explicitly requested moving the Windows session migration ahead
of the remaining final tests. The selected native rollout was found; its initial
cwd is the user home, but repeated tool workdirs identify
`C:\Users\User\CascadeProjects\donut-order-trader` as the actual project.
Do not copy the whole home directory. Five uncommitted/untracked project files
must survive; existing origin is Havkz/donut-order-trader. At that checkpoint
migration was not yet performed; see the newer entry above. The original Windows project/session must remain intact, with no
parallel Pi goal started. Remaining tests and the full audit are still required.

## 2026-09-30 Token Optimizer compatibility patch and installation

Installed the exact selected `alexgreensh/token-optimizer` v5.13.28 from pinned
commit 0b4f87e411096b4e322bd242d22fc136feac508c with a two-function installer
patch. The existing combined check now verifies real install/reinstall/uninstall
on config copies plus three sandboxed hook events; it preserves foreign hooks
and fixes root TOML placement. No replacement tool or command rewriting enabled.
Native inventory confirms ten trusted hooks, including the original seven
unchanged goal/Ponytail hashes. No model turn or service restart was performed.
The normal mapped completed TUI still opens without changing its goal/tokens;
that did not fire a fresh SessionStart and is not native hook-execution proof.
See `optimization.md` for backup paths, reproducible installation, measurements
and the remaining native-turn/compaction/Unsnooze/resource acceptance.

## 2026-09-29 optimization inventory and installer defects

Added the required `optimization.md`, grounded in native hooks/list, actual
service environment, installed source, a real goal's full-mode context and
isolated ARM64 hook measurements. Existing idle measurement was reused; no new
model turn, service restart or live mode change was needed. Total infrastructure
PSS was 370.11 MiB and CPU 10.28% of one core; final profiling remains open.

The user clarified Token Optimizer as `alexgreensh/token-optimizer` only; this
was appended to the binding goal and audit without changing prior requirements.
Release v5.13.27 was cloned for review, not globally installed. A single combined
in-memory preflight reproduces duplicate hooks on reinstall, ineffective removal
of those hooks and an incorrectly scoped appended TOML compact-prompt setting.
The real seven trusted goal/Ponytail hooks remain unchanged. Safe integration
of that exact tool is still pending; no substitute was installed.

## 2026-09-29 active-goal recovery evidence closure

The real 2026-09-28 controller SIGKILL now has active native-goal continuation
evidence, not only idle process recovery. The original session/goal survived,
resumed and completed its file/commit/push task. A read-only 2026-09-29 recheck
confirmed native/DB completion, clean tree, matching remote commit, private repo
and exactly one real Discord completion message with a Close button. See
`recovery.md` for identities, records and the explicit remaining limits.
No new fault or model request was needed for this evidence closure; existing
verifiers were extended, with no new runtime dependencies or test framework.
`1258632` passed all four GitHub Actions jobs in run `36471441990`.
Native-bridge/full-Pi restart, actual Close interaction, genuine automatic
quota-reset continuation, final audit and the delayed migration remain open.
Both read-only live rechecks passed with five mapped projects and no injected
fault. Audit reconciliation preserved the unchanged specification hash.
Graphify query/update were retried on 2026-09-29; the existing uv launcher still
fails with `Access is denied`, so graph refresh is not claimed.

## 2026-09-28 Windows heartbeat and worker recovery

`4f6ea6a` passed all four GitHub Actions jobs in run `36470494717`; deployed
worker/lifecycle/layout/audit files were hash-matched with local sources.
The existing recovery verifier now supports `--worker-restart` without new
infrastructure or a separate harness. A real idle Windows-worker stop/start
confirmed offline in 5.187s, signed reconnect in 2.954s and unchanged native
sessions, queue, manual holds and Pi services. `windows-worker.md` records the
evidence and remaining logon-autostart/silent-socket verification limits.
A one-line cold-boot heartbeat guard fixes a reproduced false-online result
before the first signed heartbeat. Its focused regression passed on Windows/Pi.
Before deployment, SQLite backup was
`backups/sqlite/codexpi-20260928-211701-1790623021781967392.db`.

## 2026-09-27/28 worker admission and top-of-dashboard usage

Windows-job submission and dispatch now share queue/manual-pause/native-goal
eligibility checks under the existing controller lock. Offline requests cannot
overwrite an inactive project's pause or human blocker. Undelivered jobs can be
cancelled during safe deletion; ambiguous sent/running jobs retain their recovery
barrier. See `windows-worker.md` for reproduction, regression and live API
evidence. Backup before deployment: `backups/code/before-worker-admission-20260927-150106.tgz`
and `backups/sqlite/codexpi-20260927-150106-1790514066026811185.db` on the Pi.

On 2026-09-28 the Usage / Limits section was moved to the first dashboard content
section, above summary/projects/queue/infrastructure, preserving its design and
data. Deployed on the Pi; the existing live Edge check passed desktop and mobile,
Weekly default, Daily switching, favicon decoding and absence of JS/CSP errors.
`state/usage-dashboard-top.png` was visually inspected. This simple layout change
adds one order assertion to the existing check, not a separate test suite.
The user's request for focused, non-granular testing is preserved in the goal.
Final migration and the complete requirement audit remain outstanding.
The required `graphify update .` was attempted but its installed uv Python launcher
returned `Access is denied` on 2026-09-28. No permissions/security settings were
changed; graph refresh remains unverified for this change package.

## 2026-09-25 usage-history implementation and live verification

`docs/usage-history.md` records the bounded persistent measurements, independent
Daily/Weekly line-area charts and remaining-usage progress cards. All 43 local
tests and 43 Pi tests (one expected skip) passed. Live responsive-browser checks,
real account samples and history persistence across controller restart passed
after the user resolved the PC VPN LAN block. An initial Linux CI cold-boot
polling defect was reproduced and fixed. A real 0% to 100% account refill was
captured later that day, without resuming the user-decision-blocked project.
The existing brand mark is also deployed as favicon.ico on login and dashboard;
actual HTTP delivery and browser decoding passed. No reference image was copied.
The earlier manual-pause correction is published as `877016b`; all four jobs in
GitHub Actions run `36056051967` passed. No overall completion is claimed.

## 2026-09-25 controller-crash verification and runbooks

The required root README and architecture/recovery runbooks were added on
2026-09-25. `Setup/verify-controller-recovery.py --crash` passed an actual idle
controller SIGKILL/systemd restart, preserving mappings/manual holds/history and
the existing dashboard login, with Discord/Windows heartbeat reconnected. Native
Codex and Unsnooze were not restarted. Details and remaining active-goal/reboot/
disaster-restore boundaries are in `docs/recovery.md`. Source commit `227c3d5`
also passed all four CI jobs in run `36168785943` (including both Linux jobs that
previously exposed the cold-boot poll bug).

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
