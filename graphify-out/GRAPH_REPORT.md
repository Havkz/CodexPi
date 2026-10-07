# Graph Report - CodexPi  (2026-10-07)

## Corpus Check
- 83 files · ~102,314 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 536 nodes · 1174 edges · 46 communities (32 shown, 14 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 100 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `72b3b47e`
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
- GoalSource
- Pi infrastructure resource measurements
- verify-sandbox.py
- Durable manual pause and real quota evidence, 2026-09-24
- main
- verify-deployment.py
- migration.py
- Bot
- usage.js
- main
- verify-usage-ui.py
- build-favicon.py
- Recovery and operator runbook
- Architecture and data ownership
- CodexPi
- DeploymentTests
- Selected Windows session migration
- test-live-lifecycle.py
- Durable manual pause and real quota evidence, 2026-09-24

## God Nodes (most connected - your core abstractions)
1. `Database` - 57 edges
2. `Controller` - 52 edges
3. `command()` - 38 edges
4. `SchedulerTests` - 36 edges
5. `atomic_write()` - 27 edges
6. `Redactor` - 25 edges
7. `finish()` - 20 edges
8. `Native` - 18 edges
9. `SignedChannel` - 16 edges
10. `CodexPi installation progress` - 16 edges

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

## Communities (46 total, 14 thin omitted)

### Community 0 - "common.py"
Cohesion: 0.29
Nodes (6): Changes, Completion gate follow-up, Lifecycle repair evidence, 2026-09-23, Reproduction and exact causes, Verification boundaries and remaining work, Verified live

### Community 2 - "windows_worker.py"
Cohesion: 0.13
Nodes (14): read_env(), execute(), main(), protect_secret(), Outbound-only native Windows executor. This process never starts an AI agent., Windows DPAPI CurrentUser; no machine-wide or plaintext key file., relative_path(), validate_job() (+6 more)

### Community 3 - "deployment.py"
Cohesion: 0.08
Nodes (39): slugify(), complete(), finish(), key(), quote(), Explicit 24/7 Pi delivery, completed through the existing lifecycle journal., Called under the controller lock, after final Git/CI checks., relocate_session() (+31 more)

### Community 4 - "Native"
Cohesion: 0.22
Nodes (8): Checks and measurements, Disabling Ponytail when explicitly requested, Hook coexistence and trust, Native execution on 2026-10-01, Optimization: installed state and acceptance limits, Pinned installation and recovery, Ponytail installation and mode, Token Optimizer: installed; native execution verified

### Community 5 - "Database"
Cohesion: 0.33
Nodes (5): Delete, Interrupted operation recovery, Project lifecycle, Rename, Verified on 2026-09-20

### Community 6 - "web.py"
Cohesion: 0.11
Nodes (24): password_hash(), password_valid(), action(), authorize(), favicon(), index(), login(), make_app() (+16 more)

### Community 7 - "dashboard.js"
Cohesion: 0.42
Nodes (16): act(), actions(), badge(), block(), button(), date(), link(), metadata() (+8 more)

### Community 8 - "CodexPi installation progress"
Cohesion: 0.12
Nodes (16): 2026-09-25 controller-crash verification and runbooks, 2026-09-25 usage-history implementation and live verification, 2026-09-27/28 worker admission and top-of-dashboard usage, 2026-09-28 Windows heartbeat and worker recovery, 2026-09-29 active-goal recovery evidence closure, 2026-09-29 optimization inventory and installer defects, 2026-09-30 Token Optimizer compatibility patch and installation, 2026-10-01 native Optimizer execution and migration priority (+8 more)

### Community 9 - "build_audit.py"
Cohesion: 0.50
Nodes (4): Installation and autostart, Protocol and jobs, Verification status, Windows worker

### Community 11 - "Bot"
Cohesion: 0.09
Nodes (29): daily_update(), idle(), Daily official CLI update, only at a proven idle single-runtime boundary., GoalSource, idle_thread(), Native, NativeError, process_in_pane() (+21 more)

### Community 21 - "main.py"
Cohesion: 0.05
Nodes (11): Database, number(), Read-only account telemetry; never decides whether a goal may execute., windows(), BaseException, DeploymentTests, Crash, LifecycleTests (+3 more)

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
Cohesion: 0.11
Nodes (28): atomic_write(), digest(), extract_project(), finish(), inspect_archive(), Explicit, journaled import of one private Windows project/native session.  No mo, Insert only absent selected-thread rows. Never replace a live DB/file., request() (+20 more)

### Community 35 - "Bot"
Cohesion: 0.33
Nodes (5): Data and boundaries, Existing-logo favicon, Presentation, Usage / Limits history, Verification as of 2026-09-25

### Community 36 - "usage.js"
Cohesion: 0.57
Nodes (6): refreshUsage(), renderUsage(), usageDate(), usageElement(), usagePercent(), usageSvg()

### Community 38 - "main"
Cohesion: 0.09
Nodes (17): canonical(), Per-connection random challenge + directional MAC + monotonic sequence., Redactor, SignedChannel, Bot, CloseView, One compact text hierarchy: vertical indentation, not a grid of fields., status_embed() (+9 more)

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

### Community 46 - "test-live-lifecycle.py"
Cohesion: 0.67
Nodes (5): main(), open_project(), Create, rename and delete ONLY a dedicated lifecycle E2E project via real UI.  P, remote(), verify_deleted()

### Community 47 - "Durable manual pause and real quota evidence, 2026-09-24"
Cohesion: 0.50
Nodes (3): Durable manual pause and real quota evidence, 2026-09-24, Pause authority, Real usage-limit history

## Knowledge Gaps
- **76 isolated node(s):** `install-base.sh script`, `PATH`, `Alltag`, `Installation und Betrieb`, `Dokumentation` (+71 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `main.py` to `Controller`, `migration.py`, `deployment.py`, `web.py`, `main`, `Bot`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `Controller` connect `Controller` to `migration.py`, `Bot`, `main.py`, `main`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `command()` connect `Controller` to `migration.py`, `deployment.py`, `main`, `web.py`, `Bot`, `main.py`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Database` (e.g. with `Controller` and `CoreTests`) actually correct?**
  _`Database` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Controller` (e.g. with `Redactor` and `Database`) actually correct?**
  _`Controller` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `command()` (e.g. with `RuntimeError` and `.fixture()`) actually correct?**
  _`command()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `SchedulerTests` (e.g. with `Redactor` and `Controller`) actually correct?**
  _`SchedulerTests` has 3 INFERRED edges - model-reasoned connections that need verification._