# Graph Report - CodexPi  (2026-10-09)

## Corpus Check
- 91 files · ~121,941 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 667 nodes · 1761 edges · 56 communities (38 shown, 18 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 197 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5183ec50`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- deployment.py
- Native
- Database
- DeploymentTests
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- Bot
- install-base.sh
- verify-dashboard.py
- __init__.py
- codexpi
- AGENTS.md
- export
- test-live-queue.py
- verify-design.py
- Design verification — 2026-09-20
- test-live-lifecycle.py
- Unsnooze integration
- Database
- GoalSource
- Pi infrastructure resource measurements
- verify-sandbox.py
- Durable manual pause and real quota evidence, 2026-09-24
- main
- verify-deployment.py
- migration.py
- Bot
- usage.js
- Bot
- send
- verify-pause-policy.py
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- test_core.py
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py
- state
- Native
- .make_controller
- DeploymentTests
- .update

## God Nodes (most connected - your core abstractions)
1. `Database` - 80 edges
2. `Controller` - 59 edges
3. `SchedulerTests` - 54 edges
4. `command()` - 42 edges
5. `atomic_write()` - 39 edges
6. `tick()` - 28 edges
7. `Native` - 28 edges
8. `Redactor` - 27 edges
9. `finish()` - 21 edges
10. `AccountVault` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `state()` --indirect_call--> `native()`  [INFERRED]
  app/web.py → Setup/verify-pause-policy.py
- `WorkerAdmissionTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_worker_server.py → app/common.py
- `DiscordTests` --uses--> `Redactor`  [INFERRED]
  tests/test_discord.py → app/common.py

## Import Cycles
- None detected.

## Communities (56 total, 18 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.10
Nodes (20): codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., boot_time(), desktop_in_use(), network_wake_since(), observation(), Windows boot identity and desktop ownership, including Session 0 workers., execute() (+12 more)

### Community 3 - "deployment.py"
Cohesion: 0.09
Nodes (47): complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session(), render() (+39 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "DeploymentTests"
Cohesion: 0.19
Nodes (6): read_env(), Redactor, main(), Run on Pi after copying reviewed sources; preserve and back up user config., Fail closed if a tracked file contains a configured secret; never print its valu, WebTests

### Community 7 - "dashboard.js"
Cohesion: 0.30
Nodes (22): accountAct(), accountPending(), act(), actions(), badge(), block(), button(), date() (+14 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.21
Nodes (8): result(), cancel_pending(), dispatch_pending(), job_denial(), submit_job(), unblock_windows(), worker_socket(), WorkerAdmissionTests

### Community 15 - "codexpi"
Cohesion: 0.19
Nodes (19): public_state(), Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error., public_state(), action(), authorize(), favicon(), index(), login() (+11 more)

### Community 23 - "verify-design.py"
Cohesion: 0.67
Nodes (3): main(), no_overflow(), Live, non-destructive browser checks; isolated headless Edge, no saved credentia

### Community 24 - "Design verification — 2026-09-20"
Cohesion: 0.40
Nodes (4): Design verification — 2026-09-20, Implemented and deployed to the Pi, Still open — not waived, Verified evidence

### Community 26 - "Unsnooze integration"
Cohesion: 0.40
Nodes (5): Auto Continue, Overnight missed wake, 2026-10-06, Unsnooze integration, Verification boundaries, Why the manual CLI wake cannot be used safely here

### Community 29 - "Pi infrastructure resource measurements"
Cohesion: 0.33
Nodes (5): 2026-10-05 redundant idle writes (local reproduction), Incremental 2026-09-29 sample, Incremental 2026-10-01 post-Optimizer sample, Pi infrastructure resource measurements, Warm idle sample (60.10 seconds)

### Community 33 - "verify-deployment.py"
Cohesion: 0.67
Nodes (3): main(), observe(), Start/observe one real deployment goal; never replace an existing objective.  De

### Community 34 - "migration.py"
Cohesion: 0.10
Nodes (46): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+38 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.44
Nodes (9): hideUsageTooltip(), refreshUsage(), renderUsage(), showUsageTooltip(), usageChart, usageDate(), usageElement(), usagePercent() (+1 more)

### Community 37 - "Bot"
Cohesion: 0.18
Nodes (7): block_summary(), Presentation only: never change native status or resume authorization., Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), DiscordTests

### Community 38 - "send"
Cohesion: 0.46
Nodes (7): eligible(), observe(), One journaled WoL boot; power commands use the existing signed worker channel., target(), tick(), wake(), send()

### Community 39 - "verify-pause-policy.py"
Cohesion: 0.67
Nodes (3): main(), native(), Live manual pause/restart/queued-resume test on one dedicated native goal.  Neve

### Community 41 - "Recovery and operator runbook"
Cohesion: 0.20
Nodes (9): Backups, Isolated SQLite restore, 2026-10-06, Live active-goal controller crash, 2026-09-28, Live controller crash, 2026-09-25, Normal process recovery, Recovery and operator runbook, Restore procedure and stop conditions, Safe diagnosis (+1 more)

### Community 42 - "Architecture and data ownership"
Cohesion: 0.40
Nodes (5): Architecture and data ownership, Modules and files, Process and trust boundaries, Queue, acknowledgement and recovery, Source of truth

### Community 43 - "CodexPi"
Cohesion: 0.40
Nodes (5): Alltag, CodexPi, Dokumentation, Entwicklung und Prüfung, Installation und Betrieb

### Community 44 - "DeploymentTests"
Cohesion: 0.33
Nodes (5): Conclusion and safe next evidence, Existing non-CodexPi services, Observed, not inferred, Separate reproducible CodexPi write-load defect, Unexpected Pi restarts — 2026-10-05

### Community 45 - "Selected Windows session migration"
Cohesion: 0.33
Nodes (5): Current evidence and unfinished verification, Fidelity and compatibility, Reusable mechanism, Scope and source, Selected Windows session migration

### Community 46 - "test_core.py"
Cohesion: 0.20
Nodes (8): canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., SignedChannel, slugify(), Generate only a password hash from the user-owned specification., CoreTests

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 49 - "export"
Cohesion: 0.08
Nodes (28): notification(), One journaled restart, then bounded observations; never replay a model request., reload_native(), command(), Controller, daily_update(), idle(), Daily official CLI update, only at a proven idle single-runtime boundary. (+20 more)

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.09
Nodes (19): RuntimeError, Probe the installed native protocol without requesting any model work., rpc(), main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted() (+11 more)

### Community 51 - "state"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 52 - "Native"
Cohesion: 0.19
Nodes (8): Native, main(), Trust only the reviewed goal/Ponytail and optional Token Optimizer definitions., main(), Pi hook inventory and isolated Ponytail checks; no model turn or live config wri, main(), Read-only live check on the Pi: real --all picker, wheel, pager and unsent draft, tmux()

### Community 53 - ".make_controller"
Cohesion: 0.33
Nodes (3): BaseException, Crash, LifecycleTests

## Knowledge Gaps
- **77 isolated node(s):** `install-base.sh script`, `PATH`, `usageChart`, `Alltag`, `Installation und Betrieb` (+72 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `export` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `Bot`, `DeploymentTests`, `Bot`, `test_core.py`, `export`, `test-live-lifecycle.py`, `.make_controller`, `DeploymentTests`, `.update`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `Controller` connect `export` to `Controller`, `windows_worker.py`, `deployment.py`, `Bot`, `DeploymentTests`, `Bot`, `Native`, `export`, `.make_controller`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `Controller` to `migration.py`, `Bot`, `DeploymentTests`, `Bot`, `export`, `test-live-lifecycle.py`, `export`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 53 inferred relationships involving `ValueError` (e.g. with `codex_login_url()` and `.__init__()`) actually correct?**
  _`ValueError` has 53 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 7 INFERRED edges - model-reasoned connections that need verification._