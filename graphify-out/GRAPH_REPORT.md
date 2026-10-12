# Graph Report - CodexPi  (2026-10-12)

## Corpus Check
- 102 files · ~138,493 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 757 nodes · 2058 edges · 53 communities (38 shown, 15 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 243 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `34ecc04a`
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
- install-base.sh
- verify-dashboard.py
- __init__.py
- codexpi-tool
- AGENTS.md
- worker_server.py
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
- controller.py
- Native
- Bot
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py
- Bot
- build_audit.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 87 edges
2. `SchedulerTests` - 65 edges
3. `Controller` - 63 edges
4. `atomic_write()` - 45 edges
5. `command()` - 45 edges
6. `Native` - 31 edges
7. `tick()` - 28 edges
8. `Worker` - 28 edges
9. `Redactor` - 27 edges
10. `NativeError` - 26 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py
- `WorkerAdmissionTests` --uses--> `Redactor`  [INFERRED]
  tests/test_worker_server.py → app/common.py

## Import Cycles
- None detected.

## Communities (53 total, 15 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.05
Nodes (10): Native, tui_proxy(), main(), Trust only the reviewed goal/Ponytail and optional Token Optimizer definitions., main(), Pi hook inventory and isolated Ponytail checks; no model turn or live config wri, main(), Read-only live check on the Pi: real --all picker, wheel, pager and unsent draft (+2 more)

### Community 2 - "windows_worker.py"
Cohesion: 0.06
Nodes (32): check(), install(), Reject paid-runner workflows before a managed Git push can trigger them., validate(), codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., ExecutionSlot, identity() (+24 more)

### Community 3 - "deployment.py"
Cohesion: 0.09
Nodes (45): complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session(), render() (+37 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 7 - "dashboard.js"
Cohesion: 0.30
Nodes (22): accountAct(), accountPending(), act(), actions(), badge(), block(), button(), date() (+14 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 21 - "worker_server.py"
Cohesion: 0.10
Nodes (27): busy(), poll(), Observe real local GitHub jobs before admitting lower-priority Windows work., register(), registrations(), setup_inventory(), setup_result(), canonical() (+19 more)

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
Cohesion: 0.09
Nodes (51): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+43 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.42
Nodes (10): hideUsageTooltip(), refreshUsage(), refreshUsageAccounts(), renderUsage(), showUsageTooltip(), usageChart, usageDate(), usageElement() (+2 more)

### Community 37 - "controller.py"
Cohesion: 0.15
Nodes (22): public_state(), Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error., public_state(), action(), authorize(), favicon(), index(), login() (+14 more)

### Community 38 - "Native"
Cohesion: 0.18
Nodes (18): digest(), extract_project(), finish(), inspect_archive(), Explicit, journaled import of one private Windows project/native session.  No mo, Insert only absent selected-thread rows. Never replace a live DB/file., request(), restore_native() (+10 more)

### Community 39 - "Bot"
Cohesion: 0.06
Nodes (27): block_summary(), password_hash(), password_valid(), Presentation only: never change native status or resume authorization., read_env(), Redactor, slugify(), Database (+19 more)

### Community 40 - "build-favicon.py"
Cohesion: 0.29
Nodes (4): GoalSource, Reuse upstream parsing and event comparison; never retain objective text., Read-only Pi resource sample; refuse to label an active-goal run as idle., sample()

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

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 48 - "verify-account-ui.py"
Cohesion: 0.67
Nodes (5): main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted()

### Community 49 - "export"
Cohesion: 0.09
Nodes (25): notification(), dispatch_ci(), One durable submission per commit; an uncertain POST is never retried., capacity_wait(), command(), Controller, daily_update(), idle() (+17 more)

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.10
Nodes (15): main(), Render the existing HTML/CSS brand mark into a multi-resolution ICO.  No referen, Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Isolated browser regression; never connects to the Pi or changes real accounts., Isolated Chromium check of real assets: chart selection must never change native, route() (+7 more)

### Community 55 - "build_audit.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

## Knowledge Gaps
- **77 isolated node(s):** `install-base.sh script`, `PATH`, `usageChart`, `Alltag`, `Installation und Betrieb` (+72 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Bot` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `Native`, `export`, `worker_server.py`, `Bot`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `Controller` to `migration.py`, `deployment.py`, `Bot`, `export`, `worker_server.py`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `Controller` connect `export` to `Controller`, `migration.py`, `windows_worker.py`, `Native`, `Bot`, `build-favicon.py`, `worker_server.py`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 67 inferred relationships involving `ValueError` (e.g. with `check()` and `install()`) actually correct?**
  _`ValueError` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 11 INFERRED edges - model-reasoned connections that need verification._