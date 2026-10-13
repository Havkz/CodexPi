# Graph Report - CodexPi  (2026-10-13)

## Corpus Check
- 105 files · ~143,687 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 789 nodes · 2158 edges · 55 communities (38 shown, 17 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 259 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `49685532`
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
- web.py
- WorkerAdmissionTests
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py
- tick
- Bot
- build_audit.py
- build_audit.py
- verify-backup-restore.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 93 edges
2. `SchedulerTests` - 68 edges
3. `Controller` - 67 edges
4. `atomic_write()` - 45 edges
5. `command()` - 45 edges
6. `Native` - 35 edges
7. `tick()` - 28 edges
8. `NativeError` - 28 edges
9. `Worker` - 28 edges
10. `Redactor` - 27 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `CoreTests` --uses--> `SignedChannel`  [INFERRED]
  tests/test_core.py → app/common.py
- `Crash` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py
- `LifecycleTests` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py

## Import Cycles
- None detected.

## Communities (55 total, 17 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.06
Nodes (32): check(), install(), Reject paid-runner workflows before a managed Git push can trigger them., validate(), codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., ExecutionSlot, identity() (+24 more)

### Community 3 - "deployment.py"
Cohesion: 0.09
Nodes (50): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+42 more)

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
Cohesion: 0.08
Nodes (31): busy(), poll(), Observe real local GitHub jobs before admitting lower-priority Windows work., register(), registrations(), setup_inventory(), setup_result(), canonical() (+23 more)

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
Nodes (54): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+46 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.42
Nodes (10): hideUsageTooltip(), refreshUsage(), refreshUsageAccounts(), renderUsage(), showUsageTooltip(), usageChart, usageDate(), usageElement() (+2 more)

### Community 38 - "web.py"
Cohesion: 0.09
Nodes (26): block_summary(), password_hash(), password_valid(), Presentation only: never change native status or resume authorization., action(), authorize(), favicon(), index() (+18 more)

### Community 39 - "WorkerAdmissionTests"
Cohesion: 0.14
Nodes (3): tui_proxy(), validate_hook_trust(), HookReviewTests

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
Cohesion: 0.06
Nodes (36): RuntimeError, main(), Render the existing HTML/CSS brand mark into a multi-resolution ICO.  No referen, configure_hooks(), gh(), install(), main(), Register the official Windows services for explicitly selected private CodexPi r (+28 more)

### Community 49 - "export"
Cohesion: 0.08
Nodes (29): notification(), dispatch_ci(), One durable submission per commit; an uncertain POST is never retried., capacity_wait(), command(), Controller, daily_update(), idle() (+21 more)

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.67
Nodes (3): fixture(), main(), Isolated Edge regression; --live only reads the Pi and opens/cancels dialogs.

### Community 52 - "tick"
Cohesion: 0.11
Nodes (15): finish(), holds_goal(), operation(), Optimizer-driven native /compact, after the current turn has finished., tick(), warning(), Native, main() (+7 more)

### Community 55 - "build_audit.py"
Cohesion: 0.17
Nodes (6): Redactor, Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), DiscordTests

### Community 56 - "build_audit.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 57 - "verify-backup-restore.py"
Cohesion: 0.33
Nodes (3): BaseException, Crash, LifecycleTests

## Knowledge Gaps
- **77 isolated node(s):** `install-base.sh script`, `PATH`, `usageChart`, `Alltag`, `Installation und Betrieb` (+72 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `controller.py` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `web.py`, `WorkerAdmissionTests`, `verify-account-ui.py`, `export`, `tick`, `worker_server.py`, `Bot`, `build_audit.py`, `verify-backup-restore.py`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `Controller` connect `export` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `controller.py`, `WorkerAdmissionTests`, `tick`, `worker_server.py`, `build_audit.py`, `verify-backup-restore.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `Controller` to `migration.py`, `controller.py`, `WorkerAdmissionTests`, `verify-account-ui.py`, `export`, `tick`, `worker_server.py`, `build_audit.py`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 69 inferred relationships involving `ValueError` (e.g. with `check()` and `install()`) actually correct?**
  _`ValueError` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 12 INFERRED edges - model-reasoned connections that need verification._