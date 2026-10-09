# Graph Report - CodexPi  (2026-10-09)

## Corpus Check
- 100 files · ~128,156 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 727 nodes · 1941 edges · 54 communities (33 shown, 21 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 233 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e60ff464`
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
- send
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
- Redactor
- DeploymentTests
- UsageTests
- build_audit.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 82 edges
2. `Controller` - 60 edges
3. `SchedulerTests` - 58 edges
4. `command()` - 44 edges
5. `atomic_write()` - 41 edges
6. `Native` - 31 edges
7. `tick()` - 28 edges
8. `Worker` - 28 edges
9. `Redactor` - 27 edges
10. `NativeError` - 22 edges

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

## Communities (54 total, 21 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.06
Nodes (32): check(), install(), Reject paid-runner workflows before a managed Git push can trigger them., validate(), codex_login_url(), Only the native managed OAuth ceremony, never an arbitrary worker/browser URL., ExecutionSlot, identity() (+24 more)

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
Nodes (44): AccountVault, auth_identity(), automatic_change(), bind_legacy_limits(), failed_resume(), finish_switch(), holds_goal(), LoginRequired (+36 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.44
Nodes (9): hideUsageTooltip(), refreshUsage(), renderUsage(), showUsageTooltip(), usageChart, usageDate(), usageElement(), usagePercent() (+1 more)

### Community 39 - "Bot"
Cohesion: 0.06
Nodes (39): public_state(), Explicit allowlist: never serialize an auth file, OAuth URL or raw RPC error., block_summary(), password_hash(), password_valid(), Presentation only: never change native status or resume authorization., read_env(), Redactor (+31 more)

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

### Community 49 - "export"
Cohesion: 0.07
Nodes (39): choose_account(), fresh_usage(), notification(), Choose a quota check or reset wait, never authorize a goal from cached usage., One journaled restart, then bounded observations; never replay a model request., Use the existing reset poll and mapped resume, not another scheduler/daemon., reload_native(), resume_account_wait() (+31 more)

### Community 50 - "test-live-lifecycle.py"
Cohesion: 0.08
Nodes (30): RuntimeError, configure_hooks(), gh(), install(), main(), Register the official Windows services for explicitly selected private CodexPi r, validate_repository(), Probe the installed native protocol without requesting any model work. (+22 more)

### Community 54 - "build_audit.py"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

## Knowledge Gaps
- **77 isolated node(s):** `install-base.sh script`, `PATH`, `usageChart`, `Alltag`, `Installation und Betrieb` (+72 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `DeploymentTests` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `send`, `Bot`, `export`, `test-live-lifecycle.py`, `Redactor`, `DeploymentTests`, `UsageTests`, `worker_server.py`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `Controller` connect `export` to `Controller`, `migration.py`, `deployment.py`, `windows_worker.py`, `DeploymentTests`, `Bot`, `Redactor`, `worker_server.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `SchedulerTests` connect `Controller` to `migration.py`, `DeploymentTests`, `Bot`, `export`, `test-live-lifecycle.py`, `worker_server.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Database` (e.g. with `Controller` and `AccountObservationTests`) actually correct?**
  _`Database` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 65 inferred relationships involving `ValueError` (e.g. with `check()` and `install()`) actually correct?**
  _`ValueError` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SchedulerTests` (e.g. with `AccountObservationTests` and `AccountSwitchTests`) actually correct?**
  _`SchedulerTests` has 9 INFERRED edges - model-reasoned connections that need verification._