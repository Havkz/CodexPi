# Graph Report - CodexPi  (2026-10-08)

## Corpus Check
- 91 files · ~118,597 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 658 nodes · 1711 edges · 49 communities (33 shown, 16 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 192 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ceb6ac5b`
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
- SchedulerTests
- verify-usage-ui.py
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- SchedulerTests
- Durable manual pause and real quota evidence, 2026-09-24
- verify-account-ui.py
- export
- test-live-lifecycle.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 77 edges
2. `Controller` - 59 edges
3. `SchedulerTests` - 51 edges
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
- `WorkerAdmissionTests` --uses--> `Redactor`  [INFERRED]
  tests/test_worker_server.py → app/common.py
- `Crash` --uses--> `Controller`  [INFERRED]
  tests/test_lifecycle.py → app/controller.py

## Import Cycles
- None detected.

## Communities (49 total, 16 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.18
Nodes (3): notification(), command(), Controller

### Community 2 - "windows_worker.py"
Cohesion: 0.10
Nodes (19): codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., boot_time(), desktop_in_use(), observation(), Windows boot identity and desktop ownership, including Session 0 workers., execute(), main() (+11 more)

### Community 3 - "deployment.py"
Cohesion: 0.09
Nodes (48): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+40 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 7 - "dashboard.js"
Cohesion: 0.30
Nodes (21): accountAct(), accountPending(), act(), actions(), badge(), block(), button(), date() (+13 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.06
Nodes (45): block_summary(), canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., Presentation only: never change native status or resume authorization., read_env(), SignedChannel (+37 more)

### Community 15 - "codexpi"
Cohesion: 0.67
Nodes (3): main(), native(), Live manual pause/restart/queued-resume test on one dedicated native goal.  Neve

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
Nodes (50): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), choose_account(), failed_resume(), finish_switch(), fresh_usage() (+42 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.57
Nodes (6): refreshUsage(), renderUsage(), usageDate(), usageElement(), usagePercent(), usageSvg()

### Community 38 - "SchedulerTests"
Cohesion: 0.05
Nodes (13): Redactor, Database, Only after confirming the original single-account identity; never guess on switc, Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed(), BaseException (+5 more)

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

### Community 46 - "SchedulerTests"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 49 - "export"
Cohesion: 0.08
Nodes (32): daily_update(), idle(), Daily official CLI update, only at a proven idle single-runtime boundary., GoalSource, idle_thread(), Native, process_in_pane(), project_thread_config() (+24 more)

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.09
Nodes (19): RuntimeError, Probe the installed native protocol without requesting any model work., rpc(), main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted() (+11 more)

## Knowledge Gaps
- **76 isolated node(s):** `install-base.sh script`, `PATH`, `Alltag`, `Installation und Betrieb`, `Dokumentation` (+71 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `SchedulerTests` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `DeploymentTests`, `Bot`, `export`, `test-live-lifecycle.py`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `windows_worker.py`, `deployment.py`, `SchedulerTests`, `Bot`, `export`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `SchedulerTests` to `Controller`, `migration.py`, `Bot`, `export`, `test-live-lifecycle.py`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `ValueError` (e.g. with `codex_login_url()` and `.__init__()`) actually correct?**
  _`ValueError` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 7 INFERRED edges - model-reasoned connections that need verification._