# Graph Report - CodexPi  (2026-10-05)

## Corpus Check
- 79 files · ~90,569 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 484 nodes · 1021 edges · 47 communities (34 shown, 13 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 90 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e8736407`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- common.py
- Controller
- windows_worker.py
- deployment.py
- Native
- Database
- web.py
- dashboard.js
- CodexPi installation progress
- build_audit.py
- connect-github.py
- Bot
- install-base.sh
- verify-dashboard.py
- __init__.py
- AGENTS.md
- main.py
- test-live-queue.py
- verify-design.py
- Design verification — 2026-09-20
- test-live-lifecycle.py
- Unsnooze integration
- Bot
- GoalSource
- Pi infrastructure resource measurements
- verify-sandbox.py
- Durable manual pause and real quota evidence, 2026-09-24
- main
- verify-deployment.py
- migration.py
- Bot
- usage.js
- build_audit.py
- main
- verify-usage-ui.py
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- test-live-lifecycle.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 51 edges
2. `Controller` - 48 edges
3. `command()` - 32 edges
4. `SchedulerTests` - 27 edges
5. `atomic_write()` - 25 edges
6. `Redactor` - 25 edges
7. `finish()` - 19 edges
8. `Native` - 16 edges
9. `CodexPi installation progress` - 15 edges
10. `Bot` - 14 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `save()`  [INFERRED]
  Setup/discord-token.py → app/lifecycle.py
- `main()` --indirect_call--> `action()`  [INFERRED]
  Setup/verify-lifecycle-fixes.py → app/web.py
- `Crash` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py
- `LifecycleTests` --uses--> `Redactor`  [INFERRED]
  tests/test_lifecycle.py → app/common.py
- `SchedulerTests` --uses--> `Redactor`  [INFERRED]
  tests/test_scheduler.py → app/common.py

## Import Cycles
- None detected.

## Communities (47 total, 13 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.33
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 1 - "Controller"
Cohesion: 0.14
Nodes (5): command(), Controller, RuntimeError, Probe the installed native protocol without requesting any model work., rpc()

### Community 2 - "windows_worker.py"
Cohesion: 0.19
Nodes (11): execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job(), Worker (+3 more)

### Community 3 - "deployment.py"
Cohesion: 0.12
Nodes (30): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+22 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.17
Nodes (19): action(), authorize(), favicon(), index(), login(), make_app(), project_detail(), safe_json() (+11 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.13
Nodes (15): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+7 more)

### Community 9 - "build_audit.py"
Cohesion: 0.40
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.08
Nodes (25): atomic_write(), canonical(), password_hash(), password_valid(), Per-connection random challenge + directional MAC + monotonic sequence., read_env(), Redactor, SignedChannel (+17 more)

### Community 21 - "main.py"
Cohesion: 0.12
Nodes (12): GoalSource, Native, NativeError, Native Codex 0.155.1 RPC and the scheduler's local TUI admission gate., Reuse upstream parsing and event comparison; never retain objective text., tui_proxy(), Read-only Pi resource sample; refuse to label an active-goal run as idle., sample() (+4 more)

### Community 23 - "verify-design.py"
Cohesion: 0.67
Nodes (3): main(), no_overflow(), Live, non-destructive browser checks; isolated headless Edge, no saved credentia

### Community 24 - "Design verification — 2026-09-20"
Cohesion: 0.40
Nodes (4): Design verification — 2026-09-20, Implemented and deployed to the Pi, Still open — not waived, Verified evidence

### Community 26 - "Unsnooze integration"
Cohesion: 0.33
Nodes (3): Unsnooze integration, Verification boundaries, Why the manual CLI wake cannot be used safely here

### Community 27 - "Bot"
Cohesion: 0.06
Nodes (10): Database, number(), Read-only account telemetry; never decides whether a goal may execute., windows(), BaseException, Crash, LifecycleTests, SchedulerTests (+2 more)

### Community 29 - "Pi infrastructure resource measurements"
Cohesion: 0.40
Nodes (4): Incremental 2026-09-29 sample, Incremental 2026-10-01 post-Optimizer sample, Pi infrastructure resource measurements, Warm idle sample (60.10 seconds)

### Community 31 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.22
Nodes (5): Evidence, 2026-09-24, Explicit Pi deployment, Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

### Community 33 - "verify-deployment.py"
Cohesion: 0.67
Nodes (3): main(), observe(), Start/observe one real deployment goal; never replace an existing objective.  De

### Community 34 - "migration.py"
Cohesion: 0.19
Nodes (18): digest(), extract_project(), finish(), inspect_archive(), Explicit, journaled import of one private Windows project/native session.  No mo, Insert only absent selected-thread rows. Never replace a live DB/file., request(), restore_native() (+10 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.57
Nodes (6): refreshUsage(), renderUsage(), usageDate(), usageElement(), usagePercent(), usageSvg()

### Community 37 - "build_audit.py"
Cohesion: 0.22
Nodes (6): Exercise the two explicitly named E2E projects through the authenticated dashboa, state(), main(), Live recovery; explicit --crash or --worker-restart injects a fault.  Never kill, main(), Resume only the existing queue E2E goal; never create or replace an objective.

### Community 38 - "main"
Cohesion: 0.43
Nodes (4): main(), Create a lossless, line-addressed audit from the user's specification.  Every no, reconcile(), AuditTests

### Community 41 - "Recovery and operator runbook"
Cohesion: 0.22
Nodes (8): Backups, Live active-goal controller crash, 2026-09-28, Live controller crash, 2026-09-25, Normal process recovery, Recovery and operator runbook, Restore procedure and stop conditions, Safe diagnosis, Verification

### Community 42 - "Architecture and data ownership"
Cohesion: 0.40
Nodes (5): Architecture and data ownership, Modules and files, Process and trust boundaries, Queue, acknowledgement and recovery, Source of truth

### Community 43 - "CodexPi"
Cohesion: 0.40
Nodes (5): Alltag, CodexPi, Dokumentation, Entwicklung und Prüfung, Installation und Betrieb

### Community 45 - "Selected Windows session migration"
Cohesion: 0.33
Nodes (5): Current evidence and unfinished verification, Fidelity and compatibility, Reusable mechanism, Scope and source, Selected Windows session migration

### Community 46 - "test-live-lifecycle.py"
Cohesion: 0.67
Nodes (5): main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted()

## Knowledge Gaps
- **68 isolated node(s):** `install-base.sh script`, `PATH`, `Alltag`, `Installation und Betrieb`, `Dokumentation` (+63 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Bot` to `Controller`, `migration.py`, `deployment.py`, `Bot`, `DeploymentTests`, `main.py`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `migration.py`, `deployment.py`, `Bot`, `main.py`, `Bot`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `migration.py`, `deployment.py`, `web.py`, `Bot`, `DeploymentTests`, `Bot`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.fixture()`) actually correct?**
  _`command()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `SchedulerTests` (e.g. with `Redactor` and `Controller`) actually correct?**
  _`SchedulerTests` has 3 INFERRED edges - model-reasoned connections that need verification._